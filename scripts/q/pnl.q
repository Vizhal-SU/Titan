/ CONFIG
envPath: getenv `LOG_DIR;
logPath: hsym `$ $[count envPath; envPath; "/home/vizhal/cpp_projects/Titan/logs"];

/ SCHEMA
colNames: `time`sym`px`qty`oid`act`side`pad1`pad2;
types: "jSiiiccxx";
widths: 8 8 4 4 4 1 1 1 1;

/ LOAD
itch: flip colNames ! (types; widths) 1: hsym `$(string logPath),"/itch.bin";

/ CLEANUP
itch: delete pad1, pad2 from itch;
/ Scale Price (Int -> Float)
itch: update px: px * 0.0001 from itch;

/ 1. CALCULATE DELTAS (Per Trade)
trades: update cash_delta: ?[side="B"; neg px*qty; px*qty], 
               inv_delta:  ?[side="B"; qty; neg qty] 
        from itch;

/ 2. CALCULATE RUNNING TOTALS (The Fix)
/ We use 'update' with 'by sym' to maintain the table structure (Flat)
/ instead of 'select' which would collapse it into nested lists.
trades: update inventory: sums inv_delta, 
               cash_balance: sums cash_delta 
        by sym from trades;

/ 3. CALCULATE FINAL PnL
/ Now the table is already flat, so we can do simple math.
pnl: select time, sym, inventory, cash_balance, 
     cum_pnl: cash_balance + (inventory * px) 
     from trades;

/ SAVE
envOut: getenv `OUT_CSV;
outPath: hsym `$ $[count envOut; envOut; "/home/vizhal/cpp_projects/Titan/logs/stats_pnl.csv"];

/ "csv" is a built-in alias for ",". 
/ We treat "pnl" as a simple table (no 0! needed as it's not keyed).
outPath 0: csv 0: pnl;

exit 0;