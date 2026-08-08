// ===========================================================================
//  MELVINN — parametric 3D-printable chassis  (TWO-LEVEL)
// ===========================================================================
//  ONE file, many parts. Set `part` (below or via the Customizer / -D on the
//  CLI) to render each piece, then File > Export > STL.
//
//    part = "deck"        LOWER deck: Pi + 2x BTS7960 + PCA9685; power bank
//                         straps under the belly; posts bolt the tier on top
//    part = "tray"        lower deck + perimeter walls (contains wiring)
//    part = "upper_tier"  SECOND LEVEL: arm + mic + batteries, on support posts
//    part = "face_plate"  vertical front face: LCD window + HC-SR04 holes
//    part = "assembly"    everything together as a preview (DON'T print this)
//    part = "deck_left" / "deck_right"   lower deck split for small beds
//
//  The two levels:
//    LOWER  – control electronics; power bank zip-tied underneath (low CoG).
//    UPPER  – the arm (front, reaching out over the top), the USB mic/speaker,
//             and both NiMH packs (strapped to the tier, hanging into the gap).
//    The tier stands on 4 posts that bolt down through the lower deck.
//
//  ⚠️  DIMENSIONS ARE A STARTING TEMPLATE, NOT A GUARANTEED FIT.
//  Only the Raspberry Pi hole pattern (58 x 49 mm, M2.5) is exact. Everything
//  tagged  // MEASURE  is a best estimate — put calipers on YOUR parts and
//  correct it. Component POSITIONS are a suggested layout; nudge the [x, y]s.
//
//  Print notes: PETG or PLA, 3-4 walls, 20-30% infill. Deck ~200 x 150 mm — if
//  it won't fit your bed, render deck_left + deck_right and pin at the seam.
// ===========================================================================

/* [What to render] */
part = "assembly"; // [deck, tray, upper_tier, face_plate, assembly, robot, deck_left, deck_right]

/* [Quality] */
$fn = 48;

// ---------------------------------------------------------------------------
//  DECK  (URDF chassis size: 200 x 150 mm)
// ---------------------------------------------------------------------------
deck_len    = 200;  // X  fore-aft
deck_wid    = 150;  // Y  side-to-side
deck_thick  = 4;    // base plate thickness
deck_fillet = 8;    // corner radius

/* [Standoffs / screws] */
post_h    = 6;      // how far boards sit above the deck (wiring clearance)
post_d    = 6;      // standoff outer diameter
m25_clear = 2.9;    // M2.5 clearance hole  (use 2.3 to self-tap into plastic)
m3_clear  = 3.4;    // M3 clearance hole

/* [Tray walls] */
wall_h = 22;
wall_t = 2.4;

/* [Upper tier / second level] */
tier_h      = 60;   // gap between the two decks (must clear the batteries)
tier_post_d = 10;
tier_screw  = 3.4;  // M3
tier_post_x = 72;   // support-post positions (clear of the wheels)
tier_post_y = 48;

// ---------------------------------------------------------------------------
//  MOTORS / WHEELS  — 4x JGA25-370 on 25 mm clamp brackets, 65 mm hex wheels
// ---------------------------------------------------------------------------
motor_integrated = false;  // false = bolt holes for the kit's 25 mm brackets
                           // true  = integrated 25 mm clamp saddles
motor_dia       = 25;      // JGA25 gearbox diameter
wheel_x         = 65;      // axle offset from centre, X   // MEASURE
wheel_y         = 68;      // half-track, Y                // MEASURE
bracket_bolt_dx = 18;      // bracket bolt spacing (along axle)  // MEASURE
bracket_bolt_d  = 3.4;     // M3

// ---------------------------------------------------------------------------
//  LOWER-DECK COMPONENTS   [ L(x), W(y) ] + mount-hole spacing [ hx, hy ].
//  MEASURE every *_hx/_hy that isn't the Pi.
// ---------------------------------------------------------------------------
// Raspberry Pi 3A+  — hole pattern EXACT: 58 x 49, M2.5
pi_l=65;  pi_w=56;  pi_hx=58;   pi_hy=49;   pi_pos=[-52, 33];  pi_rot=0;

// BTS7960 (IBT-2) H-bridge  x2                                   // MEASURE
bts_l=50; bts_w=50; bts_hx=43;  bts_hy=43;
bts_L_pos=[42, 42];  bts_R_pos=[42, -42];  bts_rot=0;

// PCA9685 16-ch servo driver  (Adafruit ~57.9 x 20.3 hole span)  // MEASURE
pca_l=62.5; pca_w=25.4; pca_hx=57.9; pca_hy=20.3; pca_pos=[-52, -33]; pca_rot=0;

// USB power bank (Redmi 20000 mAh) — zip-tied UNDER the lower deck  // MEASURE
pbank=[150, 74, 25]; pbank_pos=[0, 0];

// ---------------------------------------------------------------------------
//  SECOND-LEVEL COMPONENTS  (on / under the upper tier)
// ---------------------------------------------------------------------------
// 6-DOF arm base — on the TIER, at the front, so it reaches out over the top
arm_hx=40; arm_hy=40; arm_bolt=m3_clear; arm_pos=[48, 0]; arm_rot=0;  // MEASURE

// USB speakerphone (the "mic") — round puck on the tier, with a sound grille
mic_dia=90; mic_pos=[-46, 0];                                    // MEASURE

// NiMH packs (drive + servo) — strapped to the tier; they hang into the gap
nimh=[58, 30, 30];                                              // MEASURE
nimh_drive_pos=[6,  50];
nimh_servo_pos=[6, -50];

// --- front FACE PLATE ---
face_h   = 62;
face_w   = 100;
lcd_win  = [30.6, 40.8];   // 2.0" visible area                  // MEASURE
hcsr_dia = 16;             // ultrasonic transducer can
hcsr_sep = 26;             // centre-to-centre of the two cans    // MEASURE

/* [Split] */
split_enable = false;      // add seam dowel holes to the whole deck too

// ===========================================================================
//  PRIMITIVES
// ===========================================================================
module rrect(l, w, r) { offset(r) square([max(1,l-2*r), max(1,w-2*r)], center=true); }
module plate(l, w, t, r) { linear_extrude(t) rrect(l, w, r); }

// standoff: outer cylinder with a screw hole through it
module post(h, do, dh) {
    difference() {
        cylinder(h=h, d=do);
        translate([0,0,-0.5]) cylinder(h=h+1, d=dh);
    }
}

// four standoffs on a hx x hy rectangle, sitting on THIS deck's top (z=deck_thick)
module mount(pos, ang, hx, hy, dh=m25_clear) {
    translate([pos[0], pos[1], deck_thick]) rotate([0,0,ang])
        for (sx=[-1,1], sy=[-1,1])
            translate([sx*hx/2, sy*hy/2, 0]) post(post_h, post_d, dh);
}

// translucent ghost box for the assembly preview
module ghost(pos, ang, l, w, h=1.6, z=deck_thick+post_h) {
    translate([pos[0], pos[1], z]) rotate([0,0,ang])
        %cube([l, w, h], center=true);
}

// rounded through-slot (wire routing / straps)
module slot(pos, l, w) {
    translate([pos[0], pos[1], -1]) linear_extrude(deck_thick+2)
        rrect(l, w, min(l,w)/2 - 0.1);
}

// ===========================================================================
//  SHARED FEATURES
// ===========================================================================
module motor_bolt_holes() {          // holes for the 25 mm clamp brackets
    for (sx=[-1,1], sy=[-1,1])
        translate([sx*wheel_x, sy*wheel_y, -1])
            for (bx=[-1,1])
                translate([bx*bracket_bolt_dx/2, 0, 0])
                    cylinder(h=deck_thick+2, d=bracket_bolt_d);
}

module motor_clamps() {              // optional integrated 25 mm saddles
    for (sx=[-1,1], sy=[-1,1])
        translate([sx*wheel_x, sy*(wheel_y-6), deck_thick])
            difference() {
                translate([-12, -4, 0]) cube([24, 8, motor_dia/2+4]);
                translate([0, 10, motor_dia/2]) rotate([90,0,0])
                    cylinder(h=20, d=motor_dia);
            }
}

module tier_post_holes() {           // bolt the tier's posts down through here
    for (sx=[-1,1], sy=[-1,1])
        translate([sx*tier_post_x, sy*tier_post_y, -1])
            cylinder(h=deck_thick+2, d=tier_screw);
}

module pbank_belly_slots() {         // zip-tie the power bank under the deck
    for (sy=[-1,1])
        translate([pbank_pos[0], pbank_pos[1]+sy*pbank[1]/2, -1])
            linear_extrude(deck_thick+2) rrect(pbank[0]*0.5, 6, 3);
}

module wire_slots() {
    slot([-32,  0], 12, 40);   // central cable pass-through (to the tier)
    slot([ 20, 26], 40, 10);   // to BTS7960 L / left motors
    slot([ 20,-26], 40, 10);   // to BTS7960 R / right motors
}

module seam_dowels() {               // 4 mm pins align the two split halves
    for (sy=[-1,1])
        translate([-12, sy*45, deck_thick/2]) rotate([0,90,0])
            cylinder(h=24, d=4, center=true);
}

// ===========================================================================
//  LOWER DECK
// ===========================================================================
module deck() {
    difference() {
        union() {
            plate(deck_len, deck_wid, deck_thick, deck_fillet);
            mount(pi_pos,   pi_rot,  pi_hx,  pi_hy);
            mount(bts_L_pos,bts_rot, bts_hx, bts_hy);
            mount(bts_R_pos,bts_rot, bts_hx, bts_hy);
            mount(pca_pos,  pca_rot, pca_hx, pca_hy);
            if (motor_integrated) motor_clamps();
        }
        motor_bolt_holes();
        tier_post_holes();      // the upper tier bolts down here
        pbank_belly_slots();    // power bank straps to the underside
        wire_slots();
        if (split_enable || part == "deck_left" || part == "deck_right")
            seam_dowels();
    }
}

module tray() {
    deck();
    translate([0,0,deck_thick]) linear_extrude(wall_h)
        difference() {
            rrect(deck_len, deck_wid, deck_fillet);
            rrect(deck_len-2*wall_t, deck_wid-2*wall_t, deck_fillet-wall_t);
        }
}

// ===========================================================================
//  UPPER TIER  (second level: arm + mic + batteries on support posts)
// ===========================================================================
module upper_tier() {
    // support posts — align with tier_post_holes() in the lower deck
    for (sx=[-1,1], sy=[-1,1])
        translate([sx*tier_post_x, sy*tier_post_y, 0])
            post(tier_h, tier_post_d, tier_screw);

    // the second deck itself, sitting on top of the posts
    translate([0, 0, tier_h]) difference() {
        union() {
            plate(deck_len, deck_wid, deck_thick, deck_fillet);
            mount(arm_pos, arm_rot, arm_hx, arm_hy, arm_bolt);   // arm base
            // mic retaining ring (the puck drops into it)
            translate([mic_pos[0], mic_pos[1], deck_thick])
                difference() {
                    cylinder(h=4, d=mic_dia+8);
                    translate([0,0,-0.5]) cylinder(h=5, d=mic_dia);
                }
        }
        // mic sound / vent grille
        translate([mic_pos[0], mic_pos[1], -1])
            cylinder(h=deck_thick+2, d=mic_dia*0.55);
        // battery strap slots (two per pack; batteries hang into the gap)
        for (p=[nimh_drive_pos, nimh_servo_pos], sx=[-1,1])
            translate([p[0]+sx*nimh[0]/3, p[1], -1])
                linear_extrude(deck_thick+2) rrect(6, nimh[1]+10, 3);
        // cable pass-throughs (arm servo leads + battery wires drop down)
        translate([arm_pos[0], arm_pos[1], -1]) cylinder(h=deck_thick+2, d=14);
        translate([-6, 0, -1]) cylinder(h=deck_thick+2, d=16);
        // post screw holes through the tier deck
        for (sx=[-1,1], sy=[-1,1])
            translate([sx*tier_post_x, sy*tier_post_y, -1])
                cylinder(h=deck_thick+2, d=tier_screw);
    }
}

// ===========================================================================
//  FACE PLATE  (vertical front: LCD window + two ultrasonic holes)
// ===========================================================================
module face_plate() {
    difference() {
        translate([0, -face_w/2, 0]) cube([wall_t, face_w, face_h]);
        translate([-1, -lcd_win[0]/2, face_h/2 - lcd_win[1]/2])
            cube([wall_t+2, lcd_win[0], lcd_win[1]]);
        for (sy=[-1,1])
            translate([-1, sy*hcsr_sep/2, face_h-13]) rotate([0,90,0])
                cylinder(h=wall_t+2, d=hcsr_dia);
        for (sy=[-1,1])
            translate([-1, sy*(face_w/2-10), 8]) rotate([0,90,0])
                cylinder(h=wall_t+2, d=m3_clear);
    }
}

// ===========================================================================
//  ASSEMBLY PREVIEW  (visual only — do not export/print this)
// ===========================================================================
module assembly() {
    tier_top = deck_thick + tier_h + deck_thick;
    deck();
    // lower-deck board ghosts
    ghost(pi_pos,   pi_rot,  pi_l,  pi_w);
    ghost(bts_L_pos,bts_rot, bts_l, bts_w);
    ghost(bts_R_pos,bts_rot, bts_l, bts_w);
    ghost(pca_pos,  pca_rot, pca_l, pca_w);
    // power bank under the belly
    ghost(pbank_pos, 0, pbank[0], pbank[1], pbank[2], -pbank[2]-1);
    // front face
    translate([deck_len/2 - wall_t, 0, deck_thick]) face_plate();
    // second level
    translate([0, 0, deck_thick]) upper_tier();
    ghost(arm_pos, arm_rot, arm_hx+10, arm_hy+10, 70, tier_top);     // arm
    translate([mic_pos[0], mic_pos[1], tier_top]) %cylinder(h=26, d=mic_dia);
    ghost(nimh_drive_pos, 0, nimh[0], nimh[1], nimh[2], deck_thick+tier_h-nimh[2]-2);
    ghost(nimh_servo_pos, 0, nimh[0], nimh[1], nimh[2], deck_thick+tier_h-nimh[2]-2);
}

// ===========================================================================
//  ROBOT PREVIEW — the whole MELVINN: chassis + wheels + arm + glowing face.
//  Visual only (part = "robot"), never printed. Arm shown in its safe pose:
//  shoulder straight up, elbow folded, gripper at the top.
// ===========================================================================
module wheel() {
    rotate([90, 0, 0]) {
        color("#15171c") cylinder(h=27, d=65, center=true);      // 65 mm hex wheel
        color("#3a7bd5") cylinder(h=27.6, d=28, center=true);    // hub
    }
}

module robot() {
    assembly();
    // wheels — outboard of the deck at axle height
    for (sx=[-1, 1], sy=[-1, 1])
        translate([sx*wheel_x, sy*(deck_wid/2 + 16), 0]) wheel();
    // ultrasonic "eyes" poking through the face plate
    for (sy=[-1, 1])
        color("silver")
            translate([deck_len/2 - 6, sy*hcsr_sep/2, deck_thick + face_h - 13])
                rotate([0, 90, 0]) cylinder(h=14, d=hcsr_dia - 2);
    // LCD: dark panel + two cyan grid eyes
    color("#0a1020")
        translate([deck_len/2 + 0.6, -lcd_win[0]/2, deck_thick + face_h/2 - lcd_win[1]/2])
            cube([1, lcd_win[0], lcd_win[1]]);
    for (sy=[-1, 1])
        color("#37c8ff")
            translate([deck_len/2 + 1.4, sy*8 - 4.5, deck_thick + face_h/2 - 5])
                cube([0.8, 9, 12]);
    // the arm, on the tier mount: base joint, vertical upper arm, folded
    // forearm, wrist + gripper fingers
    tier_top = deck_thick + tier_h + deck_thick;
    translate([arm_pos[0], arm_pos[1], tier_top + post_h]) {
        color("#4a5568") cylinder(h=38, d=36);
        translate([0, 0, 38]) {
            color("#c9d1d9") translate([-9, -9, 0]) cube([18, 18, 95]);
            translate([0, 0, 95]) rotate([0, 30, 0]) {
                color("#3a7bd5") sphere(d=24);
                color("#aab2bd") translate([-8, -8, 0]) cube([16, 16, 80]);
                translate([0, 0, 80]) {
                    color("#3a7bd5") cylinder(h=18, d=20);
                    for (gy=[-1, 1])
                        color("#e23b3b")
                            translate([-6, gy*12 - 3, 18]) cube([12, 6, 30]);
                }
            }
        }
    }
}

// ===========================================================================
//  RENDER SELECTOR
// ===========================================================================
if      (part == "deck")        deck();
else if (part == "tray")        tray();
else if (part == "upper_tier")  upper_tier();
else if (part == "face_plate")  face_plate();
else if (part == "assembly")    assembly();
else if (part == "robot")       robot();
else if (part == "deck_left")
    intersection() {
        deck();
        translate([-deck_len, -deck_wid/2-10, -10])
            cube([deck_len, deck_wid+20, tier_h+wall_h+40]);
    }
else if (part == "deck_right")
    intersection() {
        deck();
        translate([0, -deck_wid/2-10, -10])
            cube([deck_len, deck_wid+20, tier_h+wall_h+40]);
    }
