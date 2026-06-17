// Reference PricingService.ComputeBasket — a CORRECT implementation used to prove the Track 2
// behavioral harness end-to-end (provision -> sandbox launch -> loopback suite -> score).
// The benchmarked model writes its own server.js; this fixture is the oracle (the Node analog of
// the Python reference in test_pricing_suite.py). Exact decimal via BigInt — no float, no decimal lib
// (the vendored closure is only grpc-js/proto-loader/pino/uuid).
'use strict';
const path = require('path');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');

const PROTO = path.join(__dirname, 'pricing.proto'); // provisioned service-relative by the harness
const pkgDef = protoLoader.loadSync(PROTO, {
  keepCase: true, longs: String, enums: Number, defaults: true, oneofs: true,
});
const pkg = grpc.loadPackageDefinition(pkgDef).startd8.bench.pricing.v1;

// ---- exact decimal (BigInt fixed-point at 10^S internal scale) ----
const S = 12n;
const SCALE = 10n ** S;

function parse(str) {
  if (typeof str !== 'string') str = String(str);
  str = str.trim();
  if (str === '') return 0n;
  let neg = false;
  if (str[0] === '-') { neg = true; str = str.slice(1); }
  else if (str[0] === '+') str = str.slice(1);
  if (!/^\d*\.?\d*$/.test(str) || str === '.') throw new Error('malformed decimal: ' + str);
  let [intp, frac = ''] = str.split('.');
  intp = intp || '0';
  frac = (frac + '0'.repeat(Number(S))).slice(0, Number(S));
  const v = BigInt(intp) * SCALE + BigInt(frac || '0');
  return neg ? -v : v;
}
const mul = (a, b) => (a * b) / SCALE;
const div = (a, b) => (a * SCALE) / b;
const pctOfScaled = (v, p) => (v * p) / (100n * SCALE);     // v * (p%) where p is internal-scaled percent
const pctOf = (v, tStr) => pctOfScaled(v, parse(tStr));

function roundToInternal(v, C, mode) {            // round to C decimals, return at internal scale
  const factor = 10n ** (S - BigInt(C));
  let q = v / factor;
  const r = v % factor;
  const rem2 = r * 2n;
  if (mode === 2 /* HALF_EVEN */) {
    if (rem2 > factor || (rem2 === factor && q % 2n === 1n)) q += 1n;
  } else { /* HALF_UP / UNSPECIFIED */
    if (rem2 >= factor) q += 1n;
  }
  return q * factor;
}
function fmt(internal, C) {
  const scaled = internal / (10n ** (S - BigInt(C)));     // exact: already rounded to C
  let s = scaled.toString();
  if (C === 0) return s;
  while (s.length <= C) s = '0' + s;
  return s.slice(0, s.length - C) + '.' + s.slice(s.length - C);
}

function computeBasket(call, callback) {
  const bad = (m) => callback({ code: grpc.status.INVALID_ARGUMENT, message: m });
  try {
    const req = call.request;
    const strategy = req.strategy;                         // 0 unspec, 1 CHAIN, 2 ADDITION
    const C = req.currency && req.currency.scale ? Number(req.currency.scale) : 2;
    const mode = req.currency ? req.currency.rounding : 0;
    const items = req.items || [];
    if (items.some((li) => (li.discounts || []).length > 0) && strategy === 0) {
      return bad('strategy required when discounts present');
    }
    let subNet = 0n, subTax = 0n;
    const outItems = [];
    for (const li of items) {
      const o = {
        sku: li.sku || '', unit_price: '', offer_unit_price: '', net_payable: '',
        tax_value: '', net_payable_with_tax: '', price_on_application: false,
        discount_value: { amount: '', percentage: '', factor_percentages: [] },
        discount_value_with_tax: { amount: '', percentage: '', factor_percentages: [] },
      };
      if (li.price_on_application) { o.price_on_application = true; outItems.push(o); continue; }

      let qty, unit;
      try { qty = parse(li.quantity); unit = parse(li.unit_price); }
      catch (e) { return bad('malformed decimal'); }
      if (qty <= 0n || unit < 0n) return bad('non-positive quantity or negative price');

      let baseUnit = unit;
      if (li.offer_unit_price && li.offer_unit_price !== '') {
        const offer = parse(li.offer_unit_price);
        if (offer > 0n && offer < unit) baseUnit = offer;
      }
      const lineBase = mul(baseUnit, qty);

      for (const d of (li.discounts || [])) {
        const n = (d.tier_factors || []).length;
        if (n < 1 || n > 4) return bad('tiers must number 1..4');
      }
      const applyDiscounts = (base) => {
        let running = base;
        for (const d of (li.discounts || [])) {
          let amt;
          if (d.kind === 1) {                              // PERCENTAGE
            if (strategy === 1) {                          // CHAIN
              let dd = running;
              for (const t of d.tier_factors) dd -= pctOf(dd, t);
              amt = running - dd;
            } else {                                       // ADDITION
              let sumP = 0n;
              for (const t of d.tier_factors) sumP += parse(t);
              amt = pctOfScaled(running, sumP);
            }
          } else {                                         // FIXED_AMOUNT (kind 2)
            amt = parse(d.tier_factors[0]);
            if (amt > running) amt = running;
          }
          if (d.maximum_amount && d.maximum_amount !== '') {
            const cap = parse(d.maximum_amount);
            if (amt > cap) amt = cap;
          }
          running -= amt;
        }
        return running;
      };

      const rate = (li.tax_rate && li.tax_rate !== '') ? parse(li.tax_rate) : 0n;
      let netI, netTaxI, taxI, discBase, discAfter;
      if (!req.calculate_tax) {
        const d = applyDiscounts(lineBase);
        netI = roundToInternal(d, C, mode); netTaxI = netI; taxI = 0n;
        discBase = lineBase; discAfter = d;
      } else if (req.discounts_pre_tax) {
        const d = applyDiscounts(lineBase);
        netI = roundToInternal(d, C, mode);
        taxI = roundToInternal(pctOfScaled(netI, rate), C, mode);
        netTaxI = netI + taxI;
        discBase = lineBase; discAfter = d;
      } else {
        const grossBase = lineBase + pctOfScaled(lineBase, rate);
        const dg = applyDiscounts(grossBase);
        netTaxI = roundToInternal(dg, C, mode);
        const onePlus = SCALE + rate / 100n;               // (1 + rate/100) at internal scale
        netI = roundToInternal(div(netTaxI, onePlus), C, mode);
        taxI = netTaxI - netI;
        discBase = grossBase; discAfter = dg;
      }

      o.unit_price = fmt(roundToInternal(unit, C, mode), C);
      if (baseUnit !== unit) o.offer_unit_price = fmt(roundToInternal(baseUnit, C, mode), C);
      o.net_payable = fmt(netI, C);
      o.tax_value = fmt(taxI, C);
      o.net_payable_with_tax = fmt(netTaxI, C);
      o.discount_value.amount = fmt(roundToInternal(discBase - discAfter, C, mode), C);
      outItems.push(o);
      subNet += netI; subTax += netTaxI;
    }
    callback(null, {
      items: outItems,
      subtotal_net_payable: fmt(subNet, C),
      subtotal_net_payable_with_tax: fmt(subTax, C),
    });
  } catch (e) {
    callback({ code: grpc.status.INTERNAL, message: String(e && e.message || e) });
  }
}

const server = new grpc.Server();
server.addService(pkg.PricingService.service, { ComputeBasket: computeBasket });
const port = process.env.PORT || '50051';
server.bindAsync('0.0.0.0:' + port, grpc.ServerCredentials.createInsecure(), (err) => {
  if (err) { console.error(err); process.exit(1); }
  server.start();
});
