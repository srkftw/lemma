"""Exercise the actual host output helpers without building the simulator."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SparseRuntimeOutput(unittest.TestCase):
    def test_checkpoint_and_export_bytes_lengths_holes_and_errors(self):
        source = (ROOT / 'sim/rtl/host/machine_runtime.cpp').read_text()
        helpers = source.split('// These helpers write only new/truncated host files,', 1)[1]
        helpers = '// These helpers write only new/truncated host files,' + helpers.split('struct Reader ', 1)[0]
        copy = 'void copy_bytes(' + source.split('void copy_bytes(', 1)[1].split('\n#define BLE_SCALARS', 1)[0]
        compiler = os.environ.get('CXX') or shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
        self.assertTrue(compiler, 'An installed C++ compiler is required; this check never downloads one')
        fixture = r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>
''' + helpers + '\n' + copy + r'''
int main(int argc,char**argv){try{
 if(argc!=2)throw std::runtime_error("output prefix required");
 std::string p=argv[1];std::vector<uint8_t>zero(16*1024*1024);
 {std::ofstream f(p+"wrapper",std::ios::binary);Writer w{f};w.u64(0x0102030405060708ULL);w.raw(zero.data(),zero.size());w.str("tail");w.vec(zero);if(!f.flush())throw std::runtime_error("fixture wrapper failed");}
 {std::ofstream f(p+"zero",std::ios::binary);Writer w{f};w.raw(zero.data(),zero.size());if(!f.flush())throw std::runtime_error("fixture zero failed");}
 {std::ifstream in(p+"wrapper",std::ios::binary),tail(p+"zero",std::ios::binary);std::ofstream out(p+"container",std::ios::binary);out.write("HDR",3);copy_bytes(in,out,32*1024*1024+28);copy_bytes(tail,out,zero.size());if(!out.flush())throw std::runtime_error("fixture container failed");}
 // A zero tail shorter than one chunk and a final nonzero byte must survive.
 {std::vector<uint8_t>mixed(65536*3+13);mixed[0]=17;mixed[65536+5]=23;mixed.back()=29;std::ofstream out(p+"mixed",std::ios::binary);Writer w{out};w.raw(mixed.data(),mixed.size());}
 std::vector<uint8_t>medium(16*1024*1024+13);medium[17]=31;medium[65533]=37;medium.back()=41;
 int fd=open((p+"medium").c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);if(fd<0||ftruncate(fd,medium.size()+11))throw std::runtime_error("fixture medium creation failed");sparse_extent(fd,medium.data(),medium.size(),11);if(close(fd))throw std::runtime_error("fixture medium close failed");
 {std::vector<uint8_t>dense(65536,7);int densefd=open((p+"dense").c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);if(densefd<0||ftruncate(densefd,dense.size()))throw std::runtime_error("fixture dense creation failed");sparse_extent(densefd,dense.data(),dense.size(),0);close(densefd);}
 bool truncated=false,failed=false,badfd=false;
 try{std::istringstream in("xx");std::ofstream out(p+"truncated",std::ios::binary);copy_bytes(in,out,3);}catch(const std::runtime_error&){truncated=true;}
 try{std::ofstream out;out.setstate(std::ios::badbit);Writer w{out};w.raw(zero.data(),zero.size());}catch(const std::runtime_error&){failed=true;}
 try{sparse_extent(-1,medium.data(),medium.size(),0);}catch(const std::runtime_error&){badfd=true;}
 if(!truncated||!failed||!badfd)throw std::runtime_error("output failure was not reported");
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
'''
        with tempfile.TemporaryDirectory(prefix='lemma-sparse-host-') as directory:
            root = Path(directory)
            unit, binary = root / 'fixture.cpp', root / 'fixture'
            unit.write_text(fixture)
            subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(binary)],
                           check=True, capture_output=True, text=True, timeout=60)
            subprocess.run([str(binary), str(root) + '/'], check=True,
                           capture_output=True, text=True, timeout=30)
            zeros = bytes(16 * 1024 * 1024)
            expected = (0x0102030405060708).to_bytes(8, 'little') + zeros
            expected += (4).to_bytes(8, 'little') + b'tail' + len(zeros).to_bytes(8, 'little') + zeros
            self.assertEqual((root / 'wrapper').read_bytes(), expected)
            self.assertEqual((root / 'zero').read_bytes(), zeros)
            self.assertEqual((root / 'container').read_bytes(), b'HDR' + expected + zeros)
            mixed = bytearray(65536 * 3 + 13)
            mixed[0], mixed[65536 + 5], mixed[-1] = 17, 23, 29
            self.assertEqual((root / 'mixed').read_bytes(), mixed)
            medium = bytearray(16 * 1024 * 1024 + 13)
            medium[17], medium[65533], medium[-1] = 31, 37, 41
            self.assertEqual((root / 'medium').read_bytes(), bytes(11) + medium)
            self.assertEqual((root / 'dense').read_bytes(), bytes([7]) * 65536)
            for name in ('wrapper', 'zero', 'container', 'medium'):
                self.assertLess((root / name).stat().st_blocks * 512, 1024 * 1024, name)


if __name__ == '__main__':
    unittest.main()
