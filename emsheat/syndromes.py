"""
Pre-specified outcome definitions (NYC final call types). Fixed before looking at 2025-26.

HEAT_CODED       the dedicated heat call type.
HEAT_SYNDROME    clinically plausible heat-related presentations, defined a priori (not from
                 the screen): unconscious/syncope, altered mental status, sick person,
                 cardiac/breathing difficulty, cardiac arrest. Code families, not single codes,
                 because NYC re-labelled within families (CARDBR from 2017 drawing from
                 DIFFBR/CARD; *FC variants 2020-23). Variants are folded into base codes with
                 model.merge_variants before summing.
                 Excluded on purpose: injuries, violence, drowning, drug, psychiatric (EDP*),
                 obstetric: they rise in summer for behavioural reasons, not heat physiology.
"""
HEAT_CODED = ["HEAT"]
HEAT_SYNDROME = ["UNC", "ALTMEN", "SICK", "DIFFBR", "CARD", "CARDBR", "RESPIR", "ARREST"]
