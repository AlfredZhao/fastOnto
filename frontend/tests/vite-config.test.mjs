import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadConfigFromFile } from 'vite';
import path from 'node:path';

const loaded = await loadConfigFromFile({command:'serve',mode:'development'}, path.resolve('vite.config.ts'));
const config = loaded.config;

test('public HTTP frontend proxies only to loopback API', () => {
  assert.equal(config.server.host, '0.0.0.0');
  assert.equal(config.server.port, 8025);
  assert.equal(config.server.strictPort, true);
  assert.equal(config.server.proxy['/api'].target, 'http://127.0.0.1:8026');
  assert.deepEqual(config.server.allowedHosts, ['localhost']);
  assert.notEqual(config.server.allowedHosts, true);
  assert.equal(config.server.cors, false);
});

test('filesystem access excludes root credentials and bootstrap secret', () => {
  assert.equal(config.server.fs.strict, true);
  assert.deepEqual(config.server.fs.allow.map(p=>path.resolve(p)), [process.cwd()]);
  assert.ok(config.server.fs.deny.includes('**/.env'));
  assert.ok(config.server.fs.deny.includes('**/.env.*'));
  assert.ok(config.server.fs.deny.includes('**/.runtime/**'));
});

test('forwarded client address cannot be spoofed through Vite', () => {
  let handler;
  config.server.proxy['/api'].configure({on: (event, callback) => { if(event==='proxyReq') handler=callback; }});
  const headers={'x-forwarded-for':'attacker-choice','x-forwarded-proto':'https','forwarded':'for=attacker',origin:'http://localhost:8025'};
  handler({setHeader:(k,v)=>headers[k.toLowerCase()]=v,removeHeader:k=>delete headers[k.toLowerCase()]},
          {socket:{remoteAddress:'127.0.0.42'},headers:{host:'localhost:8025'}});
  assert.equal(headers['x-forwarded-for'],'127.0.0.42');
  assert.equal(headers['x-forwarded-proto'],'http');
  assert.equal(headers.origin,'http://localhost:8025');
  assert.equal(headers.forwarded,undefined);
});
