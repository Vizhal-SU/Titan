/ ENV CONFIG
logPath: hsym `$getenv `LOG_DIR;
outPath: hsym `$getenv `OUT_CSV;

/ SCHEMA
schema: "JSIIIC";
ouch: flip `time`sym`sent_px`qty`oid`act ! (schema; ",") 0: hsym `$(string logPath),"/temp_ouch.csv";
itch: flip `time`sym`fill_px`qty`oid`act ! (schema; ",") 0: hsym `$(string logPath),"/temp_itch.csv";

/ FIXES
nanosPerDay: 86400000000000;
scaleFactor: 0.0001;

/ 1. Normalize Time (OUCH Only)
ouch: update time: time mod nanosPerDay from ouch;

/ 2. Scale Prices (Both)
ouch: update sent_px: sent_px * scaleFactor from ouch;
itch: update fill_px: fill_px * scaleFactor from itch;

/ JOIN
orders: `oid xkey select sent_time:time, sym, sent_px, side:act, oid from ouch;
fills:  `oid xkey select fill_time:time, fill_px, oid from itch;
merged: orders lj fills;

/ CALC SLIPPAGE
/ Slippage is the difference between what we wanted (Sent) and what we got (Fill)
/ Buy: High Fill is bad (Positive Slippage)
/ Sell: Low Fill is bad (Positive Slippage)
tca: select sent_time, sym, sent_px, fill_px, side,
     slippage: ?[side="B"; fill_px - sent_px; sent_px - fill_px] 
     from merged 
     where not null fill_time;

/ SAVE
outPath 0: csv 0: tca;
exit 0;