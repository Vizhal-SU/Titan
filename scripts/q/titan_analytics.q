/ ==============================================================================
/  TITAN KDB+ ANALYTICS BACKEND
/  Listens for real-time HFT data from C++ Engine
/ ==============================================================================

/ 1. LISTEN ON PORT 5001
\p 5001

/ 2. DEFINE SCHEMAS
/ Note: All columns initialized as empty lists to avoid 'length errors
/ Renamed 'type' -> 'msgType' to avoid reserved keyword conflict

orders: ([] time:`timespan$(); sym:`symbol$(); price:`float$(); size:`int$(); side:`char$(); orderID:`long$());

market: ([] time:`timespan$(); sym:`symbol$(); price:`float$(); size:`int$(); msgType:`char$(); side:`char$());

/ 3. UPDATE HANDLER
/ Called automatically by C++ when it sends data
/ .u.upd[`market; (time; sym; ...)]
.u.upd: {[t;x] 
    t insert x;      / Insert data into table 't'
    show x;          / Print to console (remove this in production for speed)
 };

/ 4. SERVER READY MESSAGE
-1 ">>> TITAN ANALYTICS READY ON 5001 <<<";