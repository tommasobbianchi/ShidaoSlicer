# ORCA_BELT — Report Completo: Problemi Generazione Supporti per Belt Printer

> **Scopo**: Questo documento riassume lo stato del sistema di supporti nel fork belt-printer di OrcaSlicer (ORCA_BELT). È pensato per fornire contesto completo a un modello AI o sviluppatore esterno che debba aiutare a risolvere i problemi rimanenti.

---

## 1. Contesto del Progetto

**ORCA_BELT** è un fork di OrcaSlicer che aggiunge il supporto nativo per **belt printer** (stampanti 3D a nastro trasportatore inclinato a 45°, es. IdeaFormer IR3 V2). Il progetto ha raggiunto la maturità per lo slicing base (cubo, cilindro, benchy — tutti validati fisicamente), ma la **generazione dei supporti** resta il principale ostacolo.

### Come funziona una Belt Printer

Il piano di stampa è un nastro inclinato a 45° che scorre, permettendo stampe "infinite" in una direzione. La trasformazione matematica chiave è uno **shear ZY** (non una rotazione):

```
Spazio Modello → Spazio Virtuale (V-frame):
  Y_virt = Y_model / sqrt(2)
  Z_virt = -Y_model + Z_model

Spazio Virtuale → Spazio Macchina:
  Y_mach = 2 * Y_gcode
  Z_mach = Z_gcode
```

**Gravità nello spazio virtuale**: non è [0, 0, -1] (verticale standard), ma [0, -cos(45°), -sin(45°)] = [0, -0.707, -0.707] — una diagonale che va verso -Y e -Z contemporaneamente.

### Branch e stato
- **Branch**: rescue/crash-recovery-20260128
- **Slicing base**: FUNZIONANTE, fisicamente validato
- **Supporti**: PARZIALMENTE IMPLEMENTATI, con crash e problemi geometrici

---

## 2. Architettura del Sistema di Supporti Belt

### 2.1 Tre approcci implementati in parallelo

#### A) BeltSupportMesh (Approccio "Prisma Triangolare")
**File**: src/libslic3r/BeltPrinter/BeltSupportMesh.cpp/.hpp

Genera una mesh di supporto 3D partendo dalle facce in overhang del modello:
1. Trasforma i vertici del modello nello spazio virtuale
2. Calcola il vettore gravità biased per belt a 45°: [0, -cos(theta), -sin(theta)]
3. Per ogni faccia in overhang (dove normal . gravity >= cos(90 - support_angle)), crea un prisma triangolare dalla faccia lungo la gravità fino al belt (Y=0)
4. Usa un YZ convex hull del modello per clampare i vertici floor

**Problema**: La proiezione lungo la gravità virtuale [0, -1, -1] genera supporti che si estendono enormemente in Z per facce alte nel modello.

#### B) DirectionalSupports + TreeSupport Blocker
**File**: src/libslic3r/BeltPrinter/DirectionalSupports.cpp/.hpp + TreeSupport.cpp + TreeSupport3D.cpp

Tree support standard con blocker direzionale:
1. Classifica facce della mesh per direzione rispetto al belt
2. Facce backward-facing proiettate come poligoni blocker per-layer
3. Blocker iniettati nel tree support overhang detection
4. Aggiustamenti: brim ridotto, Yv infinito, Zv_max dal profilo

**Problema**: La Y-drift dei nodi tree support CAUSA CRASH ed è stata disabilitata (TreeSupport.cpp:2889)

#### C) Gravity Envelope Clipping
**File**: src/libslic3r/Support/SupportMaterial.cpp (righe 514-616)

Post-processing: clippa supporti con inviluppo gravitazionale top-down.

### 2.2 Overhang Detection DISABILITATA in 3 punti

La detection Y-shift per gravità belt è disabilitata in PrintObject.cpp, SupportMaterial.cpp e TreeSupport.cpp/3D.cpp perché genera falsi positivi massicci al keel edge.

---

## 3. Problemi Specifici

### P1 CRITICO: Tree Support Y-Drift Crash (TreeSupport.cpp:2889)
```cpp
// ORCA_BELT: Tree support Y-drift DISABLED — causes crash.
// TODO: Re-implement tree node gravity drift properly.
#if 0
if (m_object->is_belt_printer()) {
    coord_t y_drift = -coord_t(scale_(print_z - print_z_next));
    next_layer_vertex.y() += y_drift;
}
#endif
```

Il drift 3D (TreeSupport3D.cpp:1957) FUNZIONA; quello 2D crasha.

### P2 CRITICO: Falsi Positivi Overhang al Keel Edge
L'intera faccia di contatto col belt viene rilevata come overhang.

### P3: Supporto Prismatico che Protrude in Z
Proiezione lungo gravità [0,-1,-1] genera supporti eccessivi.

### P4: Layer Count Discrepancy
156 layer OrcaSlicer vs 292 IdeaMaker per benchy.

---

## 4. Domande Aperte

1. Come risolvere il crash della Y-drift nei tree support 2D?
2. Come implementare overhang detection belt-aware senza falsi positivi?
3. Il prisma triangolare è l'approccio giusto per i supporti belt?
4. Come gestire il gap di layer count con IdeaMaker?
5. Come far lavorare insieme i 3 approcci (prisma, blocker, envelope)?

---

## 5. Validazione Supporti Monoblock (da /tmp/belt_support_validation.txt)

- 106 layer, wedge_ratio 1.000 PASS
- Supporto inizia prima del modello: PASS
- Area supporto decresce gradualmente col crescere del modello
- Funziona per geometrie semplici

---

*Report generato il 26 Febbraio 2026*
