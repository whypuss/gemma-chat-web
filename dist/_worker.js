const TARGET = "https://moggy.moggy.ccwu.cc";

export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  const targetPath = url.pathname.replace(/^\/api/, "");

  const headers = {};
  request.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (lk !== "cf-connecting-ip" && lk !== "x-forwarded-for" && lk !== "host") {
      headers[key] = value;
    }
  });

  let response;
  try {
    response = await fetch(`${TARGET}${targetPath}${url.search}`, {
      method: request.method,
      headers,
      body: request.body
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: { message: "Proxy fetch failed: " + e.message } }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  }

  const newHeaders = new Headers({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept",
    "Access-Control-Allow-Credentials": "true"
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
