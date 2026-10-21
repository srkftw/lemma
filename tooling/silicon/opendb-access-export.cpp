// SPDX-License-Identifier: Apache-2.0
// Host-only OpenROAD Tcl module: public OpenDB metadata export, no target code.
// Resolve the exact pinned executable's public C++ ABI; never inspect SWIG
// pointers or mutate source access patterns. All source/build identities belong
// to the bounded producer receipt, not to guessed runtime compatibility.
#include <tcl.h>
#include <odb/db.h>
#include <odb/dbTypes.h>
#include <algorithm>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
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
  s << '[' << r.xMin() << ',' << r.yMin() << ',' << r.xMax() << ',' << r.yMax() << ']';
}
void apids(std::ostream& s, const std::vector<odb::dbAccessPoint*>& aps) {
  s << '['; bool comma = false;
  for (auto* p : aps) { if (comma) s << ','; comma = true; s << p->getId(); }
  s << ']';
}
void boxes(std::ostream& s, odb::dbSet<odb::dbBox> geometry) {
  s << '['; bool comma = false;
  for (auto* p : geometry) {
    if (comma) s << ','; comma = true;
    s << "{\"layer\":"; quote(s, p->getTechLayer()->getName());
    s << ",\"box_nm\":[" << p->xMin() << ',' << p->yMin() << ',' << p->xMax() << ',' << p->yMax() << "]}";
  }
  s << ']';
}
void access(std::ostream& s, odb::dbAccessPoint* a) {
  s << "{\"id\":" << a->getId() << ",\"point_nm\":[" << a->getPoint().x() << ',' << a->getPoint().y() << "],\"layer\":";
  quote(s, a->getLayer()->getName());
  s << ",\"low_type\":"; quote(s, a->getLowType().getString());
  s << ",\"high_type\":"; quote(s, a->getHighType().getString());
  s << ",\"owner\":{";
  if (auto* mp = a->getMPin()) {
    s << "\"kind\":\"master_pin\",\"lib\":"; quote(s, mp->getMaster()->getLib()->getName());
    s << ",\"master\":"; quote(s, mp->getMaster()->getName());
    s << ",\"mterm\":"; quote(s, mp->getMTerm()->getName());
    s << ",\"mpin_id\":" << mp->getId();
  } else if (auto* bp = a->getBPin()) {
    s << "\"kind\":\"block_pin\",\"bterm\":"; quote(s, bp->getBTerm()->getName());
    s << ",\"bpin_id\":" << bp->getId();
  } else throw std::runtime_error("Access point has no original pin owner");
  s << "},\"directions\":[";
  std::vector<odb::dbDirection> directions; a->getAccesses(directions); bool comma = false;
  for (auto d : directions) { if (comma) s << ','; comma = true; quote(s, d.getString()); }
  s << "],\"segments\":["; comma = false;
  for (const auto& [r, begin, end] : a->getSegments()) {
    if (comma) s << ','; comma = true;
    s << "{\"rect_nm\":"; rect(s, r);
    s << ",\"begin_truncated\":" << (begin ? "true" : "false") << ",\"end_truncated\":" << (end ? "true" : "false") << '}';
  }
  s << "],\"via_groups\":["; comma = false;
  for (const auto& group : a->getVias()) {
    if (comma) s << ','; comma = true; s << '['; bool inner = false;
    for (auto* obj : group) {
      if (inner) s << ','; inner = true;
      s << "{\"id\":" << obj->getId();
      if (obj->getObjectType() == odb::dbTechViaObj) {
        auto* v = static_cast<odb::dbTechVia*>(obj);
        s << ",\"kind\":\"tech_via\",\"name\":"; quote(s, v->getName());
        s << ",\"boxes\":"; boxes(s, v->getBoxes());
      } else if (obj->getObjectType() == odb::dbViaObj) {
        auto* v = static_cast<odb::dbVia*>(obj);
        s << ",\"kind\":\"block_via\",\"name\":"; quote(s, v->getName());
        s << ",\"boxes\":"; boxes(s, v->getBoxes());
      } else throw std::runtime_error("Unexpected original access-point via object type");
      s << '}';
    }
    s << ']';
  }
  s << "]}";
}
void export_all(odb::dbDatabase* db, std::ostream& s) {
  auto* block = db->getChip() ? db->getChip()->getBlock() : nullptr;
  if (!block || block->getDbUnitsPerMicron() != 1000) throw std::runtime_error("Expected declared1000DBU original block");
  s << "{\"schema\":\"lemma-opendb-access-export/1\",\"scope\":\"Read-only public OpenDB metadata; no physical or routing qualification\",\"block\":";
  quote(s, block->getName()); s << ",\"db_units_per_micron\":1000,\"access_points\":[";
  bool comma = false;
  for (auto* ap : block->getAccessPoints()) { if (comma) s << ','; comma = true; access(s, ap); }
  s << "],\"master_pin_patterns\":["; comma = false;
  for (auto* lib : db->getLibs()) for (auto* master : lib->getMasters())
    for (auto* term : master->getMTerms()) for (auto* pin : term->getMPins()) {
      const auto patterns = pin->getPinAccess();
      if (patterns.empty()) continue;
      if (comma) s << ','; comma = true;
      s << "{\"lib\":"; quote(s, lib->getName()); s << ",\"master\":"; quote(s, master->getName());
      s << ",\"mterm\":"; quote(s, term->getName()); s << ",\"mpin_id\":" << pin->getId() << ",\"patterns\":[";
      bool inner = false;
      for (const auto& pattern : patterns) { if (inner) s << ','; inner = true; apids(s, pattern); }
      s << "]}";
    }
  s << "],\"instance_terminals\":["; comma = false;
  for (auto* inst : block->getInsts()) for (auto* term : inst->getITerms()) {
    if (comma) s << ','; comma = true;
    s << "{\"instance\":"; quote(s, inst->getName()); s << ",\"master\":"; quote(s, inst->getMaster()->getName());
    s << ",\"terminal\":"; quote(s, term->getMTerm()->getName()); s << ",\"net\":";
    if (term->getNet()) quote(s, term->getNet()->getName()); else s << "null";
    s << ",\"pattern_index\":" << inst->getPinAccessIdx() << ",\"access\":[";
    auto points = term->getAccessPoints(); std::vector<odb::dbMPin*> pins;
    for (const auto& [pin, aps] : points) pins.push_back(pin);
    std::sort(pins.begin(), pins.end(), [](auto* a, auto* b) { return a->getId() < b->getId(); });
    bool inner = false;
    for (auto* pin : pins) { if (inner) s << ','; inner = true; s << "{\"mpin_id\":" << pin->getId() << ",\"ids\":"; apids(s, points.at(pin)); s << '}'; }
    s << "],\"preferred\":"; apids(s, term->getPrefAccessPoints()); s << '}';
  }
  s << "],\"block_terminals\":["; comma = false;
  for (auto* term : block->getBTerms()) for (auto* pin : term->getBPins()) {
    if (comma) s << ','; comma = true;
    s << "{\"terminal\":"; quote(s, term->getName()); s << ",\"bpin_id\":" << pin->getId() << ",\"access\":";
    apids(s, pin->getAccessPoints()); s << '}';
  }
  s << "]}\n";
}
int command(ClientData, Tcl_Interp* interp, int objc, Tcl_Obj* const objv[]) {
  if (objc != 3 && objc != 4) { Tcl_WrongNumArgs(interp, 1, objv, "input.odb output.json ?independent-roundtrip.odb?"); return TCL_ERROR; }
  try {
    const std::string input = Tcl_GetString(objv[1]);
    const std::string output = Tcl_GetString(objv[2]);
    if (input == output || (objc == 4 && (input == Tcl_GetString(objv[3]) || output == Tcl_GetString(objv[3])))) throw std::runtime_error("Distinct source/output paths required");
    std::ifstream in(input, std::ios::binary); in.exceptions(std::ios::badbit | std::ios::failbit);
    std::unique_ptr<odb::dbDatabase, void(*)(odb::dbDatabase*)> db(odb::dbDatabase::create(), odb::dbDatabase::destroy);
    db->read(in);
    std::ofstream out(output, std::ios::binary); out.exceptions(std::ios::badbit | std::ios::failbit); export_all(db.get(), out); out.close();
    if (objc == 4) { std::ofstream roundtrip(Tcl_GetString(objv[3]), std::ios::binary); roundtrip.exceptions(std::ios::badbit | std::ios::failbit); db->write(roundtrip); roundtrip.close(); }
    Tcl_SetObjResult(interp, Tcl_NewStringObj("EXPORTED_READ_ONLY_OPENDB_ACCESS_METADATA", -1)); return TCL_OK;
  } catch (const std::exception& error) { Tcl_SetObjResult(interp, Tcl_NewStringObj(error.what(), -1)); return TCL_ERROR; }
}
}  // namespace
extern "C" int Lemmaap_Init(Tcl_Interp* interp) {
  Tcl_CreateObjCommand(interp, "lemma_ap_export", command, nullptr, nullptr);
  return Tcl_PkgProvide(interp, "lemma_ap_export", "1.0");
}
