// SPIKE FIXTURE — a Node/gRPC service (Online Boutique adservice is Java in real
// life; we use Node here to exercise the third-language extractor). It is gRPC
// auto-instrumented (→ rpc_server_duration, semconv-grpc) and declares one
// explicit OTel counter plus one prom-client counter.

const grpc = require('@grpc/grpc-js');
const { metrics } = require('@opentelemetry/api');
const client = require('prom-client');

// gRPC server auto-instrumentation → rpc_server_duration.
const server = new grpc.Server();

const meter = metrics.getMeter('adservice');
const adsServed = meter.createCounter('app_ads_served_total');

// prom-client explicit counter.
const cacheHits = new client.Counter({
  name: 'adservice_cache_hits_total',
  help: 'Ad cache hits',
});

function getAds(call, callback) {
  adsServed.add(1);
  cacheHits.inc();
  callback(null, { ads: [] });
}

module.exports = { getAds, server };
