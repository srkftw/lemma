#include "../../sim/companion/backing_peer.h"
#include <iostream>
#include <stdexcept>
int main(int argc,char**argv) {
  if (argc!=6) return 2;
  try {
    auto backing=lemma::make_peer_backing({argv[1],argv[2],argv[3],argv[4],argv[5]});
    std::vector<uint8_t> bytes(512);
    for (size_t i=0;i<bytes.size();++i) bytes[i]=static_cast<uint8_t>(i*19+7);
    auto read=backing->execute({1,10,0,512,lemma::BackingKind::Read,{}});
    if (read.error || read.transferred!=512) throw std::runtime_error("initial read");
    auto write=backing->execute({2,20,1024,512,lemma::BackingKind::Write,bytes});
    if (write.error || write.bytes!=bytes) throw std::runtime_error("write receipt");
    auto barrier=backing->execute({3,30,0,0,lemma::BackingKind::Barrier,{}});
    if (barrier.error) throw std::runtime_error("barrier receipt");
    std::vector<uint8_t> observed(512);
    backing->passive_read(1024,observed.data(),observed.size());
    if (observed!=bytes) throw std::runtime_error("observational read");
    bool rejected=false;
    try { backing->apply_recorded({2,20,1024,512,lemma::BackingKind::Write,bytes},write); }
    catch (const std::exception&) { rejected=true; }
    if (!rejected) throw std::runtime_error("external replay was accepted");
    std::cout<<"hosted Lean raw backing adapter PASS\n";
    return 0;
  } catch (const std::exception&error) { std::cerr<<error.what()<<'\n';return 1; }
}
