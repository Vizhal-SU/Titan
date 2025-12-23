/ 1. Connect to the Main Engine (Port 5001)
/ Make sure your main q process is actually running on 5001!
h: hopen 5001;

/ 2. Define the Monitor Function
monitor:{
    / Execute the queries ON THE SERVER (using handle h) and bring results back
    trades: h "select from orders where side in \"BS\"";
    
    / Get last market price from server safely
    last_px: h "$[count market; last market`price; 0n]";
    
    / --- Local Calculation (Same as before) ---
    n: count trades;
    
    buys: select sum size, sum price*size from trades where side="B";
    sells: select sum size, sum price*size from trades where side="S";
    
    b_qty: first buys`size; s_qty: first sells`size;
    b_cost: first buys`price; s_cost: first sells`price;
    
    / Handle nulls (if no trades yet)
    if[null b_qty; b_qty:0; b_cost:0f];
    if[null s_qty; s_qty:0; s_cost:0f];

    pos: b_qty - s_qty;
    
    / PnL Calculation
    / (Realized PnL) + (Unrealized PnL based on current position)
    val: (s_cost - b_cost) + (pos * last_px);
    
    -1 "--------------------------------";
    -1 "TIME       : ", string .z.T;
    -1 "TOTAL FILLS: ", string n;
    -1 "POSITION   : ", string pos;
    -1 "EST. PnL   : $", string "f"$.01 * val; 
    -1 "--------------------------------";
 }

/ 3. Run every 2 seconds
.z.ts:{monitor[]}
\t 2000