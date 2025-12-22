/*
 * Copyright (c) 1998-2022 Kx Systems Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef KX_C_H
#define KX_C_H

#ifdef __cplusplus
extern "C" {
#endif

typedef char*S,C;typedef unsigned char G;typedef short H;typedef int I;typedef long long J;typedef float E;typedef double F;typedef void V;

/*
 * K Object Structure
 * -------------------
 * type (t): 0=list, <0=atom, >0=vector
 * attribute (u): 0=none, 1=sorted, 2=unique, 3=grouped
 * reference count (r): managed by r1(x) and r0(x)
 * length (n): number of elements (if vector/list)
 * data (G0): The payload
 */
typedef struct k0{signed char m,a,t;C u;I r;union{G g;H h;I i;J j;E e;F f;S s;struct k0*k;struct{J n;G G0[1];};};}*K;

/* K object generators */
K kb(I);       // boolean
K kc(I);       // char
K kg(I);       // byte
K kh(I);       // short
K ki(I);       // int
K kj(J);       // long
K ke(F);       // real
K kf(F);       // float
K kc(I);       // char
K ks(S);       // symbol
K kd(I);       // date
K kz(F);       // datetime
K kt(I);       // time
K ktj(I,J);    // timestamp/timespan (-KJ to specify type)

/* List/Vector generators */
K knk(I,...);  // mixed list of length n
K ktn(I,J);    // typed list of length n (I=type, J=length)

/* Connection & IPC */
K k(I,const S,...); // send sync/async message
I khp(const S,I);   // connect (host, port)
I khpu(const S,I,const S); // connect with auth (host, port, user:pass)
I khpun(const S,I,const S,I); // connect with auth + timeout
V kclose(I);        // close connection

/* Reference Counting */
K r1(K); // Increment ref count
V r0(K); // Decrement ref count (free if 0)

/* Error Handling */
K krr(const S);
K orr(const S);

/* Accessors */
#define d9(f) {I i=0;F x=0;if(sizeof(F)<8){x=f;i=*(I*)&x;x=0;*(I*)&x=i;}else x=f;return x;} // internal helper
#define kG(x) ((x)->G0)
#define kC(x) kG(x)
#define kH(x) ((H*)kG(x))
#define kI(x) ((I*)kG(x))
#define kJ(x) ((J*)kG(x))
#define kE(x) ((E*)kG(x))
#define kF(x) ((F*)kG(x))
#define kS(x) ((S*)kG(x))
#define kK(x) ((K*)kG(x))

/* Types */
#define KB 1  // boolean
#define KG 4  // byte
#define KH 5  // short
#define KI 6  // int
#define KJ 7  // long
#define KE 8  // real
#define KF 9  // float
#define KC 10 // char
#define KS 11 // symbol
#define KP 12 // timestamp
#define KM 13 // month
#define KD 14 // date
#define KN 16 // timespan
#define KU 17 // minute
#define KV 18 // second
#define KT 19 // time

#ifdef __cplusplus
}
#endif

#endif // KX_C_H