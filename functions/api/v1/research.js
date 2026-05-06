export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  
  // Proxy to phone's tunnel
  const targetUrl = `https://moggy.moggy.ccwu.cc${url.pathname}${url.search}`;
  
  const headers = {};
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== 'cf-connecting-ip' && key.toLowerCase() !== 'x-forwarded-for') {
      headers[key] = value;
    }
  });
  
  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: request.body
  });
  
  const newHeaders = new Headers({
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, Accept'
  });
  
  response.headers.forEach((value, key) => {
    newHeaders.set(key, value);
  });
  
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders
  });
}
