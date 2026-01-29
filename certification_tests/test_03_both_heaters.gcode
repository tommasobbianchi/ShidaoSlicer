; CERTIFICATION TEST 1.3: Both Heaters
; Test riscaldamento simultaneo letto + ugello

M117 Test 1.3: Both Heaters
M140 S80       ; Set bed temperature
M104 S235      ; Set hotend temperature
M190 S80       ; Wait for bed
M109 S235      ; Wait for hotend
M117 Both at temp - holding 30s
G4 P30000      ; Hold for 30 seconds
M104 S0        ; Turn off hotend
M140 S0        ; Turn off bed
M117 Test 1.3 COMPLETE
