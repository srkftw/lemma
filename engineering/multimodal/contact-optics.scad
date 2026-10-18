// SPDX-License-Identifier: Apache-2.0
// Editable interface study, millimetres. No fit/force/optical qualification.
// Each electrode/optode/acoustic pad has its own replaceable sliding carrier.
// Holes are clearance envelopes, not production screw-thread definitions.
part = "assembly"; // assembly, band, contact, optical-bracket
band_radius = 95;
band_width = 22;
band_thickness = 3;
contact_travel = 6;
electrode_extension = [2,3,2,3];
optode_extension = [1,2,1,2];
acoustic_extension = [3,3];
pad_clearance = 0.4;
optical_pitch = 40;
optical_tilt = 20; // independent tablet calibration adjustment,0..35 degrees
sensor_brackets = 1; // provisional NIR sensor mounting interface,not camera count
include_tof_bracket = false;
$fn=64;
assert(band_radius>=75 && band_radius<=120);
assert(contact_travel>=2 && contact_travel<=10);
assert(optical_tilt>=0 && optical_tilt<=35);
assert(sensor_brackets>=1 && sensor_brackets<=3);
for (v=concat(electrode_extension,optode_extension,acoustic_extension))
  assert(v>=0 && v<=contact_travel);

module carrier(diameter=10,extension=2,shield=false) {
  // Independent carrier sleeve; accessible retaining flange and cable port.
  difference() {
    union() {
      cylinder(h=9,d=diameter+5);
      translate([0,0,8]) cylinder(h=2,d=diameter+9);
    }
    translate([0,0,-1]) cylinder(h=12,d=diameter+pad_clearance);
    translate([-2,-20,3]) cube([4,20,3]); // inspection/replaceable cable entry
  }
  translate([0,0,-extension]) {
    cylinder(h=9,d=diameter);
    translate([0,0,-2]) cylinder(h=2,d=diameter+2); // replaceable contact pad
    if (shield) difference() {
      translate([0,0,-3]) cylinder(h=6,d=diameter+6);
      translate([0,0,-4]) cylinder(h=8,d=diameter+2);
    }
  }
}

module band() {
  difference() {
    rotate_extrude(angle=150)
      translate([band_radius,0]) square([band_thickness,band_width]);
    // Open cleaning/inspection slots and independent contact mounting bores.
    for(a=[15,35,55,75,95,115,135])
      rotate([0,0,a]) translate([band_radius-1,-3,7]) cube([6,6,8]);
  }
  // Separate strain-relief/strap tabs; cable is removable without pad removal.
  for(a=[0,150]) rotate([0,0,a]) translate([band_radius,0,0]) difference() {
    cube([20,10,band_thickness]);
    translate([5,2,-1]) cube([10,6,band_thickness+2]);
  }
}

module optical_bracket() {
  // Tablet-mounted adjustable plate: no mandatory head-mounted camera.
  difference() {
    cube([120,25,4],center=true);
    for(x=[-50,50]) translate([x,0,-4]) cylinder(h=8,d=3.4);
  }
  for(i=[0:sensor_brackets-1])
    translate([(i-(sensor_brackets-1)/2)*optical_pitch,0,4])
    rotate([optical_tilt,0,0]) difference() {
      cube([28,16,20],center=true);
      rotate([90,0,0]) cylinder(h=30,d=14,center=true);
    }
  if(include_tof_bracket)
    translate([0,20,4]) rotate([optical_tilt,0,0]) cube([24,10,16],center=true);
}

if(part=="band") band();
if(part=="contact") carrier();
if(part=="optical-bracket") optical_bracket();
if(part=="assembly") {
  band();
  for(i=[0:3]) rotate([0,0,20+i*30]) translate([band_radius,0,band_width])
    carrier(8,electrode_extension[i],false);
  for(i=[0:3]) rotate([0,0,25+i*30]) translate([band_radius+14,0,band_width])
    carrier(6,optode_extension[i],true);
  for(i=[0:1]) rotate([0,0,5+i*140]) translate([band_radius-15,0,band_width])
    carrier(18,acoustic_extension[i],false);
  translate([-60,-70,0]) optical_bracket();
}
