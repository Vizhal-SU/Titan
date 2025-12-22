/ CONFIG
envPath: getenv `LOG_DIR;
logPath: hsym `$ $[count envPath; envPath; "/home/vizhal/cpp_projects/Titan/logs"];

/ SCHEMA
colNames: `time`sym`px`qty`oid`act`side`pad1`pad2;
types: "jSiiiccxx";
widths: 8 8 4 4 4 1 1 1 1;

/ LOAD
ouch: flip colNames ! (types; widths) 1: hsym `$(string logPath),"/ouch.bin";
itch: flip colNames ! (types; widths) 1: hsym `$(string logPath),"/itch.bin";

/ CLEANUP & JOIN
orders:    `oid xkey select sent_time:time, sym, oid from ouch;
itch_data: `oid xkey select fill_time:time, oid from itch;
merged: orders lj itch_data;

/ METRICS
data: select sent_time, sym, lat_ns:(fill_time - sent_time) 
      from merged 
      where not null fill_time, fill_time > sent_time;

/ AGGREGATE
hist: 0!select num_orders:count i by bucket:(1000 xbar lat_ns), sym from data;

/ --- FIX: FALLBACK FOR OUTPUT PATH ---
envOut: getenv `OUT_CSV;
/ If OUT_CSV is empty, save to logs/stats_latency.csv by default
outPath: hsym `$ $[count envOut; envOut; "/home/vizhal/cpp_projects/Titan/logs/stats_latency.csv"];

outPath 0: csv 0: hist;
exit 0;