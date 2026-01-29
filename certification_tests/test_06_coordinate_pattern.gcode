; Test 06: Coordinate Pattern
; Verifica mappatura assi: X=width, Y=gantry height, Z=belt (monotonic)
; Ideaformer Belt Printer Certification
;
; Pattern: traccia un "percorso" che testa tutti e 3 gli assi
; Z usa coordinate RELATIVE (G91) - sempre in avanti!

G90  ; Absolute positioning for XY

; Home position
G28 X Y

; Safe starting position (XY only)
G1 X50 Y10 F3000
G4 P500

; Switch to relative for Z movements
G91

; Simula "primo layer" - Y basso (vicino al nastro), Z avanza
G90
G1 X20 Y5 F1500
G4 P300
G1 X80 Y5 F1500
G4 P300

; Simula "strato successivo" - Y sale (gantry), Z avanza
G1 X20 Y10 F1500
G91
G1 Z5 F600    ; Belt +5mm
G90
G4 P300

G1 X80 Y10 F1500
G4 P300

; Simula "strato più alto" - Y ancora più alto, Z ancora avanti
G1 X20 Y15 F1500
G91
G1 Z5 F600    ; Belt +5mm (total +10)
G90
G4 P300

G1 X80 Y15 F1500
G4 P300

; Pattern a zigzag verticale (tipico belt print)
; X fisso, Y varia (altezza), Z avanza a step
G1 X50 Y5 F1500
G91
G1 Z5 F600    ; Belt +5mm (total +15)
G90
G4 P200

G1 X50 Y10 F1500
G4 P200

G1 X50 Y15 F1500
G4 P200

G1 X50 Y20 F1500
G4 P200

; Nuovo layer - Z avanza, ripete pattern Y
G1 X50 Y5 F1500
G91
G1 Z5 F600    ; Belt +5mm (total +20)
G90
G4 P200

G1 X50 Y10 F1500
G4 P200

G1 X50 Y15 F1500
G4 P200

; Final Z advance
G91
G1 Z5 F600    ; Belt +5mm (total +25)
G90

; Return to safe Y position (X, Y only)
G1 X50 Y10 F3000

M400
