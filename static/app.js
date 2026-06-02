const mapaIframe = document.getElementById("mapa_iframe");
const btnAplicar = document.getElementById("aplicar_filtros");
const btnRefrescar = document.getElementById("btn_refrescar");
const btnReset = document.getElementById("btn_reset");

const stats = {
  total: document.getElementById("stats_total"),
  robo: document.getElementById("stats_robo"),
  extorsion: document.getElementById("stats_extorsion"),
  agresion: document.getElementById("stats_agresion"),
  otro: document.getElementById("stats_otro"),
  actualizacion: document.getElementById("stats_actualizacion"),
  badge: document.getElementById("stats_variacion")
};

function obtenerCategoriasSeleccionadas() {
  const checks = Array.from(document.querySelectorAll("input[name='categoria']"));
  return checks.filter((c) => c.checked).map((c) => c.value);
}

function construirQuery() {
  const categorias = obtenerCategoriasSeleccionadas();
  const fechaInicio = document.getElementById("fecha_inicio").value;
  const fechaFin = document.getElementById("fecha_fin").value;

  const params = new URLSearchParams();
  categorias.forEach((cat) => params.append("categoria", cat));
  if (fechaInicio) params.append("fecha_inicio", fechaInicio);
  if (fechaFin) params.append("fecha_fin", fechaFin);
  return params.toString();
}

async function actualizarStats(query) {
  const url = query ? `/estadisticas?${query}` : "/estadisticas";
  const res = await fetch(url);
  const data = await res.json();

  stats.total.textContent = data.total ?? 0;
  stats.robo.textContent = data.categorias?.robo ?? 0;
  stats.extorsion.textContent = data.categorias?.extorsion ?? 0;
  stats.agresion.textContent = data.categorias?.agresion ?? 0;
  stats.otro.textContent = data.categorias?.otro ?? 0;
  stats.actualizacion.textContent = `Ultima actualizacion: ${data.ultima_actualizacion ?? "-"}`;
  stats.badge.textContent = "Actualizado";
}

function aplicarFiltros() {
  const query = construirQuery();
  mapaIframe.src = query ? `/mapa_folium?${query}` : "/mapa_folium";
  actualizarStats(query);
}

btnAplicar?.addEventListener("click", aplicarFiltros);
btnRefrescar?.addEventListener("click", aplicarFiltros);
btnReset?.addEventListener("click", () => {
  document.querySelectorAll("input[name='categoria']").forEach((c) => (c.checked = true));
  document.getElementById("fecha_inicio").value = "";
  document.getElementById("fecha_fin").value = "";
  aplicarFiltros();
});

window.addEventListener("load", () => {
  aplicarFiltros();
});
