/*
 * TITAN ENGINE - ARCHITECTURAL CONCEPTS CHECKLIST
 * -----------------------------------------------
 * * 1. ZERO COPY:
 * - Meaning: Accessing data without moving it from one memory buffer to another.
 * - Technique: reinterpret_cast<Struct*>(raw_buffer).
 * - Benefit: Saves memory bandwidth and CPU cycles.
 * * 2. KERNEL BYPASS:
 * - Meaning: Moving network packet processing from OS Kernel Space to User Space.
 * - Why: OS interrupts take ~3-5 microseconds. Polling a NIC takes ~100 nanoseconds.
 * * 3. CACHE LOCALITY:
 * - Meaning: Keeping data close together so the CPU pulls it all in one cache line (64 bytes).
 * - Technique: std::vector instead of std::map. Packed structs.
 * * 4. FALSE SHARING:
 * - Meaning: Two threads writing to different variables that happen to sit on the same 
 * 64-byte cache line, causing the CPU cores to fight over the cache line.
 * - Fix: alignas(64) to force variables onto their own cache lines.
 * * 5. BRANCH PREDICTION:
 * - Meaning: The CPU guessing which 'if' statement path to take before calculating it.
 * - Optimization: [[likely]] / [[unlikely]] attributes to hint the compiler.
 */