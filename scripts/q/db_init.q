/ CONFIG
envPath: getenv `LOG_DIR;
logPath: hsym `$ $[count envPath; envPath; "/home/vizhal/cpp_projects/Titan/logs"];

/ SCHEMA
/ We map the binary bytes directly to Q types.
/ j=long(8), S=sym(8), i=int(4), i=int(4), i=int(4), c=char(1), c=char(1), x=byte(1)

/ FIX: Rename 'cols' to 'colNames' to avoid reserved keyword conflict
colNames: `time`sym`px`qty`oid`act`side`pad1`pad2;

/ TYPES & WIDTHS
/ Total: 8+8+4+4+4+1+1+1+1 = 32 bytes
types: "jSiiiccxx";
widths: 8 8 4 4 4 1 1 1 1;

/ LOAD
ouch: flip colNames ! (types; widths) 1: hsym `$(string logPath),"/ouch.bin";
itch: flip colNames ! (types; widths) 1: hsym `$(string logPath),"/itch.bin";

/ CLEANUP
/ 1. Drop padding columns
/ 2. Scale Price (int -> float)
ouch: delete pad1, pad2 from ouch;
itch: delete pad1, pad2 from itch;

ouch: update px: px * 0.0001 from ouch;
itch: update px: px * 0.0001 from itch;

/ DISPLAY
-1 ">>> OUCH TABLE (32-Byte Aligned) <<<";
show 5#ouch;

-1 "";
-1 ">>> ITCH TABLE (32-Byte Aligned) <<<";
show 5#itch;

exit 0;