; Test Prime Line "L" - IdeaMaker Style v2
; Prime line a forma di L con setup PETG
; Ideaformer Belt Printer Certification
;
; Pattern:
;   1. Linea verticale: 10mm in Z (nastro avanza), Y=0.4, X=0
;   2. Linea orizzontale destra: 250mm in X, Y=0.4, Z ferma
;   3. Linea orizzontale sinistra: 250mm in X (ritorno), Y=0.4, Z ferma
;
; MODIFICHE v2:
;   - Estrusione aumentata del 20% (E * 1.2)
;   - Z avanza +20mm a fine stampa (separazione oggetti)

; === HOMING FIRST ===
G28           ; Home all axes (required!)

; === SETUP PETG ===
; Hotend: 240°C
; Bed: 80°C
; Layer height: 0.3mm
; Line width: 0.4mm
; Speed: 40mm/s

; Riscaldamento simultaneo DOPO homing
M140 S80          ; Avvia bed
M104 S240         ; Avvia hotend
M190 S80          ; Attende bed
M109 S240         ; Attende hotend
M117 Ready for prime line

; Absolute positioning for XY
G90

; Move to starting position (X=0, Y=0.4 - primo layer height)
; Y=0.4 significa ugello molto vicino al nastro
G1 X0 Y0.4 F3000
G4 P500

; Reset extruder
G92 E0

; === PARTE 1: Linea verticale (10mm in Z) ===
; FASE 1a: Crea BLOB ANCHOR MASSICCIO (20mm!)
M117 Prime: MASSIVE BLOB ANCHOR
G1 E5.0 F150  ; Estrude 5mm velocità normale
G4 P2000      ; Pausa 2s
G1 E10.0 F150 ; Estrude altri 5mm (totale 10mm)
G4 P2000      ; Pausa 2s
G1 E15.0 F150 ; Estrude altri 5mm (totale 15mm)
G4 P2000      ; Pausa 2s
G1 E20.0 F150 ; Estrude ultimi 5mm (totale 20mm BLOB MASSICCIO!)
G4 P3000      ; Pausa 3s finale per blob solidificazione

; FASE 1b: Z avanza mentre estrude
M117 Prime: vertical extrusion
G1 F2400  ; 40mm/s
G91       ; Relative per Z
G1 Z10 E28.0  ; Nastro avanza 10mm + estrude 8mm (totale 28mm verticale)
G90       ; Torna absolute

G4 P200

; === PARTE 2: Linea orizzontale DESTRA (250mm in X) ===
; Z ferma, Y=0.4 costante, X da 0 a 250
M117 Prime line: horizontal right
G1 X250 Y0.4 E58.0 F2400  ; 250mm a destra + 30mm estrusione (28+30)
G4 P200

; === PARTE 3: Linea orizzontale SINISTRA (250mm ritorno) ===
; Z ferma, Y=0.4 costante, X da 250 a 0
M117 Prime line: horizontal left
G1 X0 Y0.4 E88.0 F2400    ; 250mm a sinistra + 30mm estrusione (total 88mm)
G4 P200

; Retrazione intermedia
G1 E85.0 F1200  ; Retrazione 3mm

; Alza ugello (Y più alto per sicurezza)
G1 Y10 F3000

M117 Prime line complete!

; === SEPARAZIONE OGGETTO: Avanza nastro +20mm ===
; Z avanza per separare la prime line dal prossimo oggetto
M117 Advancing belt for separation
G91           ; Relative positioning
G1 Z20 F600   ; Nastro avanza +20mm (separazione)
G90           ; Torna absolute

M117 Ready for next print!

; === RETRAZIONE ANTI-OOZING ESTREMA + TEMPERATURA ===
; Step 1: ABBASSA TEMPERATURA SUBITO (riduce pressione)
M104 S180     ; Abbassa hotend a 180°C (riduce oozing immediatamente)
M117 Cooling + retracting

; Step 2: Retrazione MASSIMA 20mm rapida
G1 E65.0 F3000  ; Retrazione RAPIDISSIMA 20mm (da 85.0 a 65.0)
G4 P500

; Step 3: Retrazione lenta extra 10mm
G1 E55.0 F400   ; Retrazione LENTA 10mm extra (totale 30mm!)
G4 P1000        ; Pausa lunga

; Step 4: Alza ugello MOLTO lontano
G1 Y50 F3000    ; Y=50mm (massima distanza)

; Spegni hotend (opzionale - dipende se continui a stampare)
; M104 S0  ; Uncomment per spegnere hotend

M117 Print complete - no oozing!

; === NOTE ===
; - Estrusione aumentata per migliore adesione prime line
; - Z avanza 20mm per separare oggetti
; - Retrazione finale 8mm previene oozing
; - Belt infinita: separazione sempre possibile!

M400

