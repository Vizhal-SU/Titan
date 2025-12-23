checkLag:{[]
  now:.z.p;
  m_last:$[count market; exec last time from market; 0Np];
  o_last:$[count orders; exec last time from orders; 0Np];
  
  -1 "--- SYSTEM TIME: ",(string now)," ---";
  -1 "Market Last Time: ",$[(null m_last); "EMPTY"; string m_last];
  -1 "Orders Last Time: ",$[(null o_last); "EMPTY"; string o_last];
  
  if[not null m_last; -1 "Market Lag    : ", string now - m_last];
  if[not null o_last; -1 "Orders Lag    : ", string now - o_last];
 }