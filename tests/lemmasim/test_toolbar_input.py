"""Literal nine-tool input/pixel observations; no compiled-guest claim."""
from importlib.machinery import SourceFileLoader
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from notebook_input import Input, generate
from check_notebook_workflow import check_toolbar_pixels
spec = importlib.util.spec_from_file_location('nine_native_input', ROOT / 'scripts/check_lemmasim_native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
loader = SourceFileLoader('nine_fault_input', str(ROOT / 'scripts/check_lemmasim_faults.py'))
spec = importlib.util.spec_from_loader(loader.name, loader)
faults = importlib.util.module_from_spec(spec)
loader.exec_module(faults)


class NineToolInput(unittest.TestCase):
    def test_each_literal_center_hits_its_guest_tool_on_both_geometries(self):
        for width, height, centers in ((1650, 2200, [91,274,457,640,823,1006,1189,1372,1555]),
                                       (1404, 1872, [78,234,390,546,702,858,1014,1170,1326])):
            stream = Input(width, height, 200000000, 100000, 200000000)
            for button, center in enumerate(centers):
                stream.tool(button, f'literal{button}')
                down, up = stream.events[-2:]
                self.assertEqual(down[2], (center * 65535 + width - 2) // (width - 1))
                self.assertEqual(down[2] * (width - 1) // 65535 // (width // 9), button)
                self.assertEqual(down[3] * (height - 1) // 65535, 64)
                self.assertEqual((down[5], up[5], up[4]), (3, 2, 0))
            for invalid in (-1,9,True,1.0):
                with self.assertRaises(ValueError): stream.tool(invalid, 'invalid')

    def test_save_and_compact_are_separate_actual_tool_inputs(self):
        _, basic = generate('basic',1650,2200,200000000,100000,200000000)
        self.assertEqual(basic['input_samples'],53)
        self.assertEqual([a['button'] for a in basic['actions'] if a['kind']=='tool'],[7])
        self.assertEqual(basic['expected']['retained_raw_samples'],50)
        _, editing = generate('editing',1650,2200,200000000,100000,200000000)
        self.assertEqual(editing['actions'][-1]['button'],7)
        self.assertNotIn(8,[a['button'] for a in editing['actions'] if a['kind']=='tool'])
        data, workload = generate('workload',1650,2200,200000000,100000,200000000)
        self.assertEqual(workload['input_samples'],100035)
        self.assertEqual([(a['button'],a['name']) for a in workload['actions'][-2:]],
                         [(7,'save durable state'),(8,'compact committed records')])
        self.assertEqual(workload['expected']['retained_raw_samples'],100000)
        self.assertEqual([a['raw_samples'] for a in workload['actions'] if a['kind']=='stroke'],[6250]*16)
        self.assertEqual(len(data),100035*72)

    def test_checkpoint_fault_reference_targets_only_explicit_compact(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, manifest = faults.raw_fixture(Path(folder), 'checkpoint')
            row = struct.unpack_from('<9Q', raw.read_bytes(),72)
            pixel = row[2] * 1649 // 65535
            self.assertEqual(pixel,1555)
            self.assertEqual(pixel//183,8)
            action = json.loads(manifest.read_text())['actions'][0]
            self.assertEqual(action['button'],8)
            self.assertEqual(action['name'],'compact committed records')

    def test_native_pointer_scaling_uses_queried_geometry(self):
        self.assertEqual(native.toolbar_point(1650,2200,7),(27263,954))
        self.assertEqual(native.toolbar_point(1650,2200,8),(30900,954))
        self.assertEqual(native.toolbar_point(1404,1872,7),(27326,1121))
        self.assertEqual(native.toolbar_point(1404,1872,8),(30969,1121))
        for width,height in ((1650,2200),(1404,1872)):
            for button in range(9):
                x,y=native.toolbar_point(width,height,button)
                pixel=x*65535//32767*(width-1)//65535
                self.assertEqual(pixel//(width//9),button)
                self.assertLess(y*65535//32767*(height-1)//65535,128)
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            (directory/'process.json').write_text(json.dumps({'qmp_socket':str(directory/'literal.sock')}))
            def qmp(endpoint,command,arguments):
                self.assertEqual(command,'pmemsave')
                self.assertEqual((arguments['val'],arguments['size']),(0x10010020,16))
                Path(arguments['filename']).write_bytes(struct.pack('<2Q',1404,1872))
            with patch.object(native.sim,'qmp',side_effect=qmp),patch.object(native,'pointer') as pointer:
                command=native.toolbar_pointer(directory,8,True)
                self.assertEqual(command,{'x':30969,'y':1121,'down':True})
                pointer.assert_called_once_with(directory,30969,1121,True)
        for invalid in [(511,2200,7),(1650,319,7),(1650,2200,9),(1650,2200,True)]:
            with self.assertRaises(ValueError): native.toolbar_point(*invalid)


class LiteralToolbarPixels(unittest.TestCase):
    def pixels(self,width,height):
        # Expected visible rows written independently; no production glyph or
        # raster implementation is imported into this oracle fixture.
        glyphs=[['101','101','111','101','101'],['010','100','111','100','010'],
                ['010','001','111','001','010'],['101','101','101','101','111'],
                ['110','101','110','101','101'],['111','100','110','100','111'],
                ['101','101','101','111','111'],['111','100','111','001','111'],
                ['111','100','100','100','111']]
        pixels=bytearray([255])*(width*height*3)
        for button,rows in enumerate(glyphs):
            for row,pattern in enumerate(rows):
                for col,bit in enumerate(pattern):
                    x=button*(width//9)+25+col*12;y=37+row*12
                    pixels[(y*width+x)*3:(y*width+x)*3+3]=bytes([0 if bit=='1' else 255])*3
        return pixels

    def test_nine_literal_glyphs_match_both_geometries(self):
        for width,height in ((1650,2200),(1404,1872)):
            check_toolbar_pixels(width,height,bytes(self.pixels(width,height)))

    def test_old_layout_or_compact_painted_as_save_fails_closed(self):
        width,height=1650,2200; pixels=self.pixels(width,height)
        x=8*183+25+12;y=37+24
        pixels[(y*width+x)*3:(y*width+x)*3+3]=b'\0\0\0'
        with self.assertRaisesRegex(ValueError,'control8'):
            check_toolbar_pixels(width,height,bytes(pixels))
        with self.assertRaises(ValueError): check_toolbar_pixels(width,height,bytes([255])*(width*height*3))
        with self.assertRaisesRegex(ValueError,'geometry or length'):
            check_toolbar_pixels(width,height,bytes(pixels[:-1]))


if __name__ == '__main__': unittest.main()
