/ ==============================================================================
/  TITAN KDB+ ANALYTICS BACKEND
/  Schema Alignment: STRICT MATCH
/ ==============================================================================

/ 1. LISTEN ON PORT 5001
\p 5001

/ 2. CLEAR STATE
delete orders, market from `.;

/ 3. DEFINE FINAL SCHEMA
/ Note: 'time' must be timespan$() because C++ sends type -16 (ktj -KN)

orders: ([] 
    time:`timestamp$();   / Matches Type -16
    sym:`symbol$();      / Matches Type -11
    price:`float$();     / Matches Type -9
    size:`int$();        / Matches Type -6
    side:`char$();       / Matches Type -10
    orderID:`long$()     / Matches Type -7
 );

market: ([] 
    time:`timestamp$();   / Matches Type -16
    sym:`symbol$();      / Matches Type -11
    price:`float$();     / Matches Type -9
    size:`int$();        / Matches Type -6
    msgType:`char$();    / Matches Type -10
    side:`char$()        / Matches Type -10
 );

/ 4. PRODUCTION HANDLER
.u.upd: {[t;x] 
    // x[1]: `$rtrim string x[1];  / Cast to string -> Trim -> Cast back to Symbol
    t insert x; 
 };

-1 ">>> TITAN ANALYTICS: SCHEMA SYNCHRONIZED <<<";