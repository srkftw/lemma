// SPDX-License-Identifier: Apache-2.0
// Read-only HOST manufacturing tool. Resolve the exact pinned OpenROAD public
// ABI. This is neither target code nor an independent OpenDB implementation.
// In particular, retain native RECT dimensions and every via cut layer that
// the Python wire-decoder binding cannot independently return.
#include <tcl.h>
#include <odb/db.h>
#include <odb/dbShape.h>
#include <odb/dbWireCodec.h>
#include <filesystem>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void quote(std::ostream& s, const std::string& value) {
  s << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') s << '\\' << c;
    else if (c < 32) {
      static const char hex[] = "0123456789abcdef";
      s << "\\u00" << hex[c >> 4] << hex[c & 15];
    } else s << c;
  }
  s << '"';
}
void rect(std::ostream& s, const odb::Rect& r) {
  if (r.xMin() >= r.xMax() || r.yMin() >= r.yMax())
    throw std::runtime_error("Nonpositive native mask rectangle");
  s << '[' << r.xMin() << ',' << r.yMin() << ',' << r.xMax() << ',' << r.yMax() << ']';
}
void shape(std::ostream& s, const char* kind, odb::dbTechLayer* layer,
           const odb::Rect& r, bool& comma) {
  if (!layer) throw std::runtime_error("Native mask layer missing");
  if (comma) s << ','; comma = true;
  s << "{\"kind\":"; quote(s, kind);
  s << ",\"layer\":"; quote(s, layer->getName());
  s << ",\"rect_nm\":"; rect(s, r); s << '}';
}
void export_geometry(odb::dbDatabase* db, std::ostream& s) {
  auto* block = db->getChip() ? db->getChip()->getBlock() : nullptr;
  if (!block || block->getDbUnitsPerMicron() != 1000)
    throw std::runtime_error("Expected declared1000DBU original block");
  s << "{\"schema\":\"lemma-opendb-native-geometry/1\",\"db_units_per_micron\":1000,\"top\":";
  quote(s, block->getName()); s << ",\"nets\":[";
  bool net_comma = false;
  for (auto* net : block->getNets()) {
    if (net_comma) s << ','; net_comma = true;
    s << "{\"name\":"; quote(s, net->getName());
    s << ",\"type\":"; quote(s, net->getSigType().getString());
    s << ",\"iterms\":["; bool comma = false;
    for (auto* iterm : net->getITerms()) {
      if (comma) s << ','; comma = true;
      s << '['; quote(s, iterm->getInst()->getName()); s << ',';
      quote(s, iterm->getMTerm()->getName()); s << ']';
    }
    s << "],\"bterms\":["; comma = false;
    for (auto* bterm : net->getBTerms()) {
      if (comma) s << ','; comma = true; quote(s, bterm->getName());
    }
    s << "],\"shapes\":["; comma = false;
    unsigned patches = 0, wire_shapes = 0, via_count = 0;
    if (auto* wire = net->getWire()) {
      // The shape iterator treats RECT as a segment and returns its complete
      // native rectangle; the independent decoder below checks its dimensions.
      odb::dbWireShapeItr it; odb::dbShape current; it.begin(wire);
      while (it.next(current)) {
        if (current.isVia()) {
          ++via_count;
          std::vector<odb::dbShape> boxes;
          odb::dbShape::getViaBoxes(current, boxes);
          if (boxes.empty()) throw std::runtime_error("Native via has no boxes");
          for (const auto& box : boxes)
            shape(s, "signal_via", box.getTechLayer(), box.getBox(), comma);
        } else if (current.isSegment()) {
          ++wire_shapes;
          shape(s, "signal_wire_or_rect", current.getTechLayer(), current.getBox(), comma);
        } else throw std::runtime_error("Unqualified native wire shape");
      }
      odb::dbWireDecoder decoder; decoder.begin(wire);
      bool positioned = false; int x = 0, y = 0;
      while (true) {
        auto op = decoder.next();
        if (op == odb::dbWireDecoder::END_DECODE) break;
        switch (op) {
          case odb::dbWireDecoder::PATH: positioned = false; break;
          case odb::dbWireDecoder::JUNCTION:
          case odb::dbWireDecoder::SHORT:
          case odb::dbWireDecoder::VWIRE: {
            auto point = wire->getCoord(decoder.getJunctionValue());
            x = point.x(); y = point.y(); positioned = true; break;
          }
          case odb::dbWireDecoder::POINT: decoder.getPoint(x, y); positioned = true; break;
          case odb::dbWireDecoder::POINT_EXT: {
            int extension; decoder.getPoint(x, y, extension); positioned = true; break;
          }
          case odb::dbWireDecoder::RECT: {
            if (!positioned) throw std::runtime_error("Native RECT missing origin");
            int a,b,c,d; decoder.getRect(a,b,c,d);
            // Export this second native observation explicitly; the consumer
            // requires its full rectangle in the shape-iterator multiset.
            shape(s, "decoder_rect_witness", decoder.getLayer(),
                  odb::Rect(x+a,y+b,x+c,y+d), comma); ++patches; break;
          }
          case odb::dbWireDecoder::VIA:
          case odb::dbWireDecoder::TECH_VIA:
          case odb::dbWireDecoder::ITERM:
          case odb::dbWireDecoder::BTERM:
          case odb::dbWireDecoder::RULE: break;
          default: throw std::runtime_error("Unknown native wire opcode");
        }
      }
    }
    unsigned special_boxes = 0;
    for (auto* swire : net->getSWires()) for (auto* box : swire->getWires()) {
      ++special_boxes;
      if (box->isVia()) {
        std::vector<odb::dbShape> boxes; box->getViaBoxes(boxes);
        if (boxes.empty()) throw std::runtime_error("Native special via has no boxes");
        for (const auto& geometry : boxes)
          shape(s, "special_via", geometry.getTechLayer(), geometry.getBox(), comma);
      } else shape(s, "special_wire", box->getTechLayer(), box->getBox(), comma);
    }
    s << "],\"wire_shape_count\":" << wire_shapes << ",\"wire_via_count\":" << via_count
      << ",\"RECT_count\":" << patches << ",\"special_box_count\":" << special_boxes << '}';
  }
  s << "],\"ports\":["; bool comma = false;
  for (auto* terminal : block->getBTerms()) for (auto* pin : terminal->getBPins()) {
    if (comma) s << ','; comma = true;
    s << "{\"terminal\":"; quote(s, terminal->getName());
    s << ",\"net\":";
    if (terminal->getNet()) quote(s, terminal->getNet()->getName()); else s << "null";
    s << ",\"shapes\":["; bool inside = false;
    for (auto* box : pin->getBoxes()) {
      if (box->isVia()) throw std::runtime_error("Unqualified via block pin");
      shape(s, "port", box->getTechLayer(), box->getBox(), inside);
    }
    s << "]}";
  }
  s << "]}\n";
}
int command(ClientData, Tcl_Interp* interp, int objc, Tcl_Obj* const objv[]) {
  if (objc != 3 && objc != 4) {
    Tcl_WrongNumArgs(interp,1,objv,"input.odb output.json ?independent-roundtrip.odb?"); return TCL_ERROR;
  }
  try {
    const std::string input=Tcl_GetString(objv[1]), output=Tcl_GetString(objv[2]);
    if (input==output || (objc==4 && (input==Tcl_GetString(objv[3]) || output==Tcl_GetString(objv[3]))))
      throw std::runtime_error("Distinct source/output paths required");
    if (std::filesystem::exists(output) || (objc==4 && std::filesystem::exists(Tcl_GetString(objv[3]))))
      throw std::runtime_error("Unused output paths required");
    std::ifstream in(input,std::ios::binary); in.exceptions(std::ios::badbit|std::ios::failbit);
    std::unique_ptr<odb::dbDatabase,void(*)(odb::dbDatabase*)> db(odb::dbDatabase::create(),odb::dbDatabase::destroy);
    db->read(in);
    std::ofstream out(output,std::ios::binary); out.exceptions(std::ios::badbit|std::ios::failbit);
    export_geometry(db.get(),out); out.close();
    if (objc==4) {
      std::ofstream copy(Tcl_GetString(objv[3]),std::ios::binary); copy.exceptions(std::ios::badbit|std::ios::failbit);
      db->write(copy); copy.close();
    }
    Tcl_SetObjResult(interp,Tcl_NewStringObj("EXPORTED_READ_ONLY_NATIVE_GEOMETRY",-1)); return TCL_OK;
  } catch (const std::exception& error) {
    Tcl_SetObjResult(interp,Tcl_NewStringObj(error.what(),-1)); return TCL_ERROR;
  }
}
} // namespace
extern "C" int Lemmageometry_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp,"lemma_geometry_export",command,nullptr,nullptr);
  return Tcl_PkgProvide(interp,"lemma_geometry_export","1.0");
}
