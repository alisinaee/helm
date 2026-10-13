// Hash routes: "#/" is Home, "#/p/<id>" is a project. Anything else falls back to Home.

const PROJECT_ROUTE = /^#\/p\/([a-z0-9][a-z0-9-]{0,39})$/;

export function parseRoute(hash) {
  const match = PROJECT_ROUTE.exec(hash || "");
  if (match) return { name: "project", id: match[1] };
  return { name: "home", id: null };
}

export function currentRoute() {
  return parseRoute(window.location.hash);
}

export function homeHash() {
  return "#/";
}

export function projectHash(id) {
  return "#/p/" + id;
}

export function onRouteChange(handler) {
  window.addEventListener("hashchange", handler);
}
