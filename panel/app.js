/* Panel de selección de personal: Cargar, Candidatos, Asistente y Ejecuciones.
   Todo pasa por la API del mismo servidor (motor propio en Python, sin n8n). */
(() => {
  "use strict";
  const API = (window.APP_CONFIG && window.APP_CONFIG.API_URL) || "";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v) => `${Math.round((Number(v) || 0) * 100)} %`;
  const TIPOS_IMAGEN = ["image/jpeg", "image/png", "image/webp"];
  const NOMBRES_CAMPOS = {
    profesion: "Profesión", experiencia_anios: "Años de experiencia", habilidades: "Habilidades",
    educacion: "Educación", certificaciones: "Certificaciones",
  };

  const estado = {
    sistema: null,
    permisos: { subir: true, ver_imagenes: true, auditoria: true },
    archivos: [], // {id, file, tipo: "pdf"|"foto", nombre, correo, estado, mensaje}
    candidatos: [],
    pendientes: [],
    colaRevision: [],
  };

  // ───────────────────────── API ─────────────────────────
  async function api(ruta, opciones = {}) {
    let r;
    try {
      r = await fetch(API + ruta, { credentials: "same-origin", ...opciones });
    } catch {
      throw new Error("No hay conexión con el servidor. Revisa que esté encendido.");
    }
    const tipo = r.headers.get("content-type") || "";
    const datos = tipo.includes("json") ? await r.json().catch(() => ({})) : null;
    if (!r.ok) {
      const msg = (datos && (datos.mensaje || (typeof datos.detail === "string" && datos.detail))) || `Error ${r.status}`;
      const e = new Error(msg); e.status = r.status; throw e;
    }
    return datos;
  }

  // ───────────────────────── Pestañas ─────────────────────────
  const tabs = () => $$('[role="tab"]').filter((t) => !t.hidden);
  function abrirTab(tab) {
    $$('[role="tab"]').forEach((t) => {
      const activo = t === tab;
      t.setAttribute("aria-selected", activo);
      t.tabIndex = activo ? 0 : -1;
      const panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) panel.hidden = !activo;
    });
    if (tab.id === "tab-candidatos") cargarCandidatos();
    if (tab.id === "tab-ejecuciones") cargarEjecuciones();
    if (tab.id === "tab-asistente") $("#pregunta").focus();
  }
  $$('[role="tab"]').forEach((t) => {
    t.addEventListener("click", () => abrirTab(t));
    t.addEventListener("keydown", (e) => {
      const lista = tabs(); const i = lista.indexOf(t);
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const sig = lista[(i + (e.key === "ArrowRight" ? 1 : -1) + lista.length) % lista.length];
        sig.focus(); abrirTab(sig);
      }
    });
  });

  // ───────────────────────── Estado del servidor ─────────────────────────
  async function comprobar() {
    const conn = $("#conn"), txt = $("#connTexto");
    try {
      const s = await api("/api/estado");
      estado.sistema = s;
      const partes = ["Conectado al servidor"];
      partes.push(s.modelos.length ? `IA: ${s.modelos.join(" → ")}` : "IA sin configurar");
      partes.push(s.ocr ? "OCR listo" : "OCR no instalado");
      txt.textContent = partes.join(" · ");
      conn.dataset.estado = s.modelos.length && s.ocr ? "ok" : "aviso";
      llenarCargos(s.cargos);
      $("#dropAyuda").textContent = `PDF de hasta ${s.max_pdf_mb} MB o fotos JPG/PNG de hasta ${s.max_imagen_mb} MB. Puedes subir varios a la vez.`;
    } catch (e) {
      conn.dataset.estado = "error";
      txt.textContent = e.message;
    }
  }

  async function cargarSesion() {
    try {
      const s = await api("/api/sesion");
      estado.permisos = s.permisos;
      $("#tab-ejecuciones").hidden = s.rol !== "admin";
    } catch {
      $("#tab-ejecuciones").hidden = false; // sin capa de seguridad (app.main:app en desarrollo)
    }
  }

  function llenarCargos(cargos) {
    const sel = $("#cargo"), filtro = $("#filtroCargo");
    const previo = sel.value;
    sel.innerHTML = cargos.map((c) => `<option>${esc(c)}</option>`).join("");
    if (previo) sel.value = previo;
    const f = filtro.value;
    filtro.innerHTML = '<option value="">Todos</option>' + cargos.map((c) => `<option>${esc(c)}</option>`).join("");
    filtro.value = f;
  }

  // ───────────────────────── Cargar ─────────────────────────
  const drop = $("#drop"), inputArchivos = $("#archivos"), inputCamara = $("#camara");
  drop.addEventListener("click", () => inputArchivos.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputArchivos.click(); } });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("encima"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("encima"); }));
  drop.addEventListener("drop", (e) => agregarArchivos(e.dataTransfer.files));
  inputArchivos.addEventListener("change", () => { agregarArchivos(inputArchivos.files); inputArchivos.value = ""; });
  $("#btnCamara").addEventListener("click", () => inputCamara.click());
  inputCamara.addEventListener("change", () => { agregarArchivos(inputCamara.files); inputCamara.value = ""; });

  let contador = 0;
  function agregarArchivos(lista) {
    const aviso = $("#avisoArchivos");
    const rechazados = [];
    for (const file of lista) {
      const nombre = file.name.toLowerCase();
      const esPdf = file.type === "application/pdf" || nombre.endsWith(".pdf");
      const esFoto = TIPOS_IMAGEN.includes(file.type) || /\.(jpe?g|png|webp)$/.test(nombre);
      if (/\.(heic|heif)$/.test(nombre)) { rechazados.push(`${file.name}: las fotos HEIC no se pueden leer; en el iPhone elige Ajustes > Cámara > Formatos > «Más compatible».`); continue; }
      if (!esPdf && !esFoto) { rechazados.push(`${file.name}: solo se aceptan PDF, JPG, PNG o WebP.`); continue; }
      estado.archivos.push({ id: ++contador, file, tipo: esPdf ? "pdf" : "foto", nombre: "", correo: "", estado: "nuevo", mensaje: "" });
    }
    aviso.hidden = !rechazados.length;
    aviso.textContent = rechazados.join(" ");
    pintarArchivos();
  }

  function pintarArchivos() {
    const ul = $("#listaArchivos");
    ul.innerHTML = estado.archivos.map((a) => `
      <li class="file" data-id="${a.id}" data-estado="${a.estado}">
        <span class="tipo ${a.tipo}">${a.tipo === "pdf" ? "PDF" : "FOTO"}</span>
        <p class="nombre-archivo" title="${esc(a.file.name)}">${esc(a.file.name)} · ${(a.file.size / 1024 / 1024).toFixed(2)} MB</p>
        <button type="button" class="btn ghost mini quitar" aria-label="Quitar ${esc(a.file.name)}" ${a.estado === "enviando" ? "disabled" : ""}>Quitar</button>
        <input type="text" placeholder="Nombre del candidato" aria-label="Nombre del candidato de ${esc(a.file.name)}" data-campo="nombre" value="${esc(a.nombre)}" ${a.estado !== "nuevo" && a.estado !== "error" ? "disabled" : ""}>
        <input type="email" placeholder="correo@ejemplo.com" aria-label="Correo del candidato de ${esc(a.file.name)}" data-campo="correo" value="${esc(a.correo)}" ${a.estado !== "nuevo" && a.estado !== "error" ? "disabled" : ""}>
        ${a.mensaje ? `<p class="estado-envio">${a.mensaje}</p>` : ""}
      </li>`).join("");
    $("#btnQuitarEnviados").hidden = !estado.archivos.some((a) => a.estado === "ok" || a.estado === "revision");
    actualizarBoton();
  }

  $("#listaArchivos").addEventListener("input", (e) => {
    const li = e.target.closest(".file"); if (!li) return;
    const a = estado.archivos.find((x) => x.id === Number(li.dataset.id));
    a[e.target.dataset.campo] = e.target.value;
    actualizarBoton();
  });
  $("#listaArchivos").addEventListener("click", (e) => {
    if (!e.target.classList.contains("quitar")) return;
    const id = Number(e.target.closest(".file").dataset.id);
    estado.archivos = estado.archivos.filter((a) => a.id !== id);
    pintarArchivos();
  });
  $("#btnQuitarEnviados").addEventListener("click", () => {
    estado.archivos = estado.archivos.filter((a) => a.estado !== "ok" && a.estado !== "revision");
    pintarArchivos();
  });
  $("#autorizacion").addEventListener("change", actualizarBoton);

  const porEnviar = () => estado.archivos.filter((a) => a.estado === "nuevo" || a.estado === "error");
  function actualizarBoton() {
    const lista = porEnviar();
    const completos = lista.every((a) => a.nombre.trim().length >= 3 && /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(a.correo.trim()));
    const btn = $("#btnEnviar");
    btn.disabled = !lista.length || !completos || !$("#autorizacion").checked;
    btn.textContent = lista.length ? `Enviar ${lista.length} archivo${lista.length > 1 ? "s" : ""}` : "Enviar hojas de vida";
    const r = $("#resumenEnvio");
    if (lista.length && !completos) r.textContent = "Escribe nombre y correo de cada candidato.";
    else if (lista.length && !$("#autorizacion").checked) r.textContent = "Marca la autorización de datos para enviar.";
    else if (!r.dataset.fijo) r.textContent = "";
  }

  $("#formCargar").addEventListener("submit", async (e) => {
    e.preventDefault();
    const lista = porEnviar();
    if (!lista.length) return;
    $("#btnEnviar").disabled = true;
    const resumen = $("#resumenEnvio");
    resumen.dataset.fijo = "1";
    let ok = 0, revision = 0, errores = 0;
    for (const a of lista) {
      a.estado = "enviando"; a.mensaje = a.tipo === "pdf" ? "Leyendo el PDF y consultando la IA…" : "Leyendo la foto con OCR y consultando la IA…";
      pintarArchivos();
      const form = new FormData();
      form.append(a.tipo === "pdf" ? "Archivo" : "Imagen", a.file, a.file.name);
      form.append("Nombre", a.nombre.trim());
      form.append("Correo", a.correo.trim());
      form.append("Cargo", $("#cargo").value);
      form.append("Autorizacion", "true");
      try {
        const r = await api(a.tipo === "pdf" ? "/api/candidatos" : "/api/vision", { method: "POST", body: form });
        if (a.tipo === "pdf" || r.estado === "guardado") {
          const c = a.tipo === "pdf" ? r : r.candidato;
          a.estado = "ok"; ok++;
          a.mensaje = `✓ Guardado como <strong>${esc(c.candidato_id)}</strong> · puntaje ${esc(c.puntaje)} · ${esc(c.estado)}${c.aviso_telegram ? " · aviso enviado por Telegram" : ""}${c.modelo ? ` · IA: ${esc(c.modelo)}` : ""}`;
        } else {
          a.estado = "revision"; revision++; a.lecturaId = r.lectura_id;
          a.mensaje = `La lectura necesita revisión humana (lectura ${esc(r.lectura_id)}). ${esc((r.lectura.motivos || []).join(" "))}`;
          estado.colaRevision.push(r.lectura_id);
        }
      } catch (err) {
        a.estado = "error"; errores++;
        a.mensaje = `✗ ${esc(err.message)}`;
      }
      pintarArchivos();
    }
    resumen.textContent = [ok && `${ok} guardado(s)`, revision && `${revision} por revisar`, errores && `${errores} con error`].filter(Boolean).join(" · ");
    delete resumen.dataset.fijo;
    actualizarBoton();
    comprobar();
    siguienteRevision();
  });

  // ───────────────────────── Candidatos ─────────────────────────
  async function cargarCandidatos() {
    const aviso = $("#avisoCandidatos");
    try {
      const [cands, pend] = await Promise.all([api("/api/candidatos"), api("/api/vision?estado=pendiente")]);
      estado.candidatos = cands; estado.pendientes = pend;
      aviso.hidden = true;
    } catch (e) {
      aviso.hidden = false; aviso.textContent = e.message;
    }
    pintarCandidatos(); pintarPendientes();
  }

  function pintarPendientes() {
    const sec = $("#pendientes");
    sec.hidden = !estado.pendientes.length;
    $("#listaPendientes").innerHTML = estado.pendientes.map((p) => `
      <li>
        <div class="info"><strong>${esc(p.nombre)}</strong> · ${esc(p.cargo)}
          <small>Lectura ${p.id} · ${esc(p.archivo_original)} · OCR ${pct(p.confianza_ocr)} · subida por ${esc(p.subido_por)}${p.ia_pendiente ? " · la IA no respondió (en cola de reintento)" : ""}</small></div>
        ${estado.permisos.subir ? `<button type="button" class="btn mini primary" data-revisar="${p.id}">Revisar</button>` : ""}
      </li>`).join("");
  }
  $("#listaPendientes").addEventListener("click", (e) => {
    const id = e.target.dataset.revisar; if (id) abrirRevision(Number(id));
  });

  function pintarCandidatos() {
    const q = $("#buscar").value.trim().toLowerCase();
    const cargo = $("#filtroCargo").value, orden = $("#orden").value;
    let filas = estado.candidatos.filter((c) =>
      (!cargo || c.cargo === cargo) &&
      (!q || [c.nombre, c.profesion, c.habilidades, c.cargo, c.candidato_id, c.educacion].join(" ").toLowerCase().includes(q)));
    filas.sort(orden === "puntaje" ? (a, b) => b.puntaje - a.puntaje || b.experiencia_anios - a.experiencia_anios
      : orden === "nombre" ? (a, b) => a.nombre.localeCompare(b.nombre) : (a, b) => b.id - a.id);
    const badge = $("#badge");
    badge.hidden = !estado.candidatos.length; badge.textContent = estado.candidatos.length;
    $("#conteo").textContent = estado.candidatos.length ? `${filas.length} de ${estado.candidatos.length} candidatos` : "";
    $("#vacio").hidden = estado.candidatos.length > 0;
    $("#listaCandidatos").innerHTML = filas.map((c) => {
      const habs = String(c.habilidades || "").split(",").map((h) => h.trim()).filter(Boolean).slice(0, 10);
      const foto = c.origen === "foto" && c.lectura_id && estado.permisos.ver_imagenes
        ? `<a href="${API}/api/vision/${c.lectura_id}/imagen" target="_blank" rel="noopener">Ver foto original</a>` : "";
      return `<li class="cand">
        <div class="cand-cab">
          <div class="puntaje" data-zona="${esc(c.zona)}" style="--p:${Number(c.puntaje) || 0}" aria-label="Puntaje ${esc(c.puntaje)} de 100"><span>${esc(c.puntaje)}</span></div>
          <div>
            <h3>${esc(c.nombre)}</h3>
            <p class="sub">${esc(c.candidato_id)} · ${esc(c.cargo)}</p>
            <div class="etiquetas"><span class="chip" data-zona="${esc(c.zona)}">${esc(c.estado)}</span>
              <span class="chip ${c.origen === "foto" ? "foto" : "pdf"}">${c.origen === "foto" ? "Foto · visión" : "PDF"}</span></div>
          </div>
        </div>
        <p><strong>${esc(c.profesion)}</strong> · ${esc(c.experiencia_anios)} años de experiencia</p>
        <div class="habs">${habs.map((h) => `<span>${esc(h)}</span>`).join("")}</div>
        <p>${esc(c.justificacion)}</p>
        <details><summary>Más detalles</summary>
          <dl><dt>Resumen</dt><dd>${esc(c.resumen)}</dd><dt>Educación</dt><dd>${esc(c.educacion)}</dd>
          <dt>Certificaciones</dt><dd>${esc(c.certificaciones)}</dd><dt>Correo</dt><dd>${esc(c.correo)}</dd>
          <dt>Archivo</dt><dd>${esc(c.archivo)}</dd><dt>Modelo IA</dt><dd>${esc(c.modelo || "—")}</dd></dl>
        </details>
        <div class="cand-pie"><span>${esc((c.fecha || "").replace("T", " ").slice(0, 16))} UTC</span>${foto}</div>
      </li>`;
    }).join("");
  }
  ["input", "change"].forEach((ev) => ["#buscar", "#filtroCargo", "#orden"].forEach((s) => $(s).addEventListener(ev, pintarCandidatos)));
  $("#btnActualizar").addEventListener("click", cargarCandidatos);

  // ───────────────────────── Revisión humana de fotos ─────────────────────────
  const dlg = $("#dlgRevision");
  let lecturaActual = null;

  function siguienteRevision() {
    if (dlg.open || !estado.colaRevision.length) return;
    abrirRevision(estado.colaRevision.shift());
  }

  async function abrirRevision(id) {
    let lect;
    try { lect = await api(`/api/vision/${id}`); } catch (e) { alertaLista(e.message); return; }
    lecturaActual = lect;
    const umbral = (estado.sistema && estado.sistema.umbrales.campo) || 0.6;
    $("#revSub").textContent = `${lect.nombre} · ${lect.cargo} · ${lect.archivo_original} · lectura OCR ${pct(lect.confianza_ocr)}${lect.modelo ? ` · IA: ${lect.modelo}` : ""}`;
    const fig = $(".rev-foto");
    if (estado.permisos.ver_imagenes && lect.tiene_imagen) {
      fig.innerHTML = '<img id="revImagen" alt="Foto subida del formulario"><figcaption>Compara con lo que se leyó. La foto se borra si descartas la lectura.</figcaption>';
      $("#revImagen").src = `${API}/api/vision/${id}/imagen?t=${Date.now()}`;
    } else {
      fig.innerHTML = '<div class="rev-sin-foto">La foto no está disponible.</div>';
    }
    $("#revMotivos").innerHTML = (lect.motivos || []).map((m) => `<li>${esc(m)}</li>`).join("");
    $("#revMotivos").hidden = !(lect.motivos || []).length;
    $("#revCampos").innerHTML = Object.entries(NOMBRES_CAMPOS).map(([campo, etiqueta]) => {
      const valor = lect.campos[campo] ?? "";
      const conf = Number(lect.confianza[campo] ?? 0);
      const dudoso = conf < umbral;
      const control = campo === "experiencia_anios"
        ? `<input type="number" min="0" max="60" id="rev-${campo}" value="${esc(valor === "" ? 0 : valor)}">`
        : campo === "profesion"
          ? `<input type="text" id="rev-${campo}" value="${esc(valor)}">`
          : `<textarea id="rev-${campo}" rows="2">${esc(valor)}</textarea>`;
      return `<div class="rev-campo ${dudoso ? "dudoso" : ""}">
        <label for="rev-${campo}"><span>${etiqueta}</span><span class="conf">${dudoso ? "Dudoso · " : ""}confianza ${pct(conf)}</span></label>
        ${control}<div class="barra-conf"><i style="width:${Math.round(conf * 100)}%"></i></div></div>`;
    }).join("");
    $("#revError").hidden = true;
    const descartar = $("#revDescartar");
    descartar.classList.remove("confirmar"); descartar.textContent = "Descartar lectura";
    dlg.showModal();
  }

  function alertaLista(msg) {
    const aviso = $("#avisoCandidatos"); aviso.hidden = false; aviso.textContent = msg;
  }

  async function accionRevision(ruta, cuerpo) {
    const err = $("#revError");
    $$(".rev-pie button").forEach((b) => (b.disabled = true));
    try {
      const r = await api(ruta, cuerpo ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) } : { method: "POST" });
      marcarArchivo(lecturaActual.id, r);
      dlg.close();
      cargarCandidatos();
      siguienteRevision();
    } catch (e) {
      err.hidden = false; err.textContent = e.message;
    } finally {
      $$(".rev-pie button").forEach((b) => (b.disabled = false));
    }
  }

  function marcarArchivo(lecturaId, r) {
    const a = estado.archivos.find((x) => x.lecturaId === lecturaId);
    if (!a) return;
    if (r.estado === "guardado") {
      a.estado = "ok";
      a.mensaje = `✓ Revisado y guardado como <strong>${esc(r.candidato_id)}</strong> · puntaje ${esc(r.candidato.puntaje)} · ${esc(r.candidato.estado)}${r.corregido ? " · con correcciones" : ""}`;
    } else {
      a.mensaje = "Lectura descartada: la foto se borró del servidor.";
    }
    pintarArchivos();
  }

  $("#revConfirmar").addEventListener("click", () => {
    const campos = {};
    Object.keys(NOMBRES_CAMPOS).forEach((c) => (campos[c] = $(`#rev-${c}`).value));
    accionRevision(`/api/vision/${lecturaActual.id}/confirmar`, { campos });
  });
  $("#revDescartar").addEventListener("click", (e) => {
    const b = e.currentTarget;
    if (!b.classList.contains("confirmar")) { b.classList.add("confirmar"); b.textContent = "¿Seguro? Se borra la foto"; return; }
    accionRevision(`/api/vision/${lecturaActual.id}/rechazar`);
  });
  $("#revDespues").addEventListener("click", () => { dlg.close(); cargarCandidatos(); });
  dlg.addEventListener("close", () => setTimeout(siguienteRevision, 200));

  // ───────────────────────── Asistente ─────────────────────────
  const SUGERENCIAS = [
    "¿Quién tiene el mejor puntaje?",
    "¿Qué candidatos saben SQL?",
    "Compara a los preseleccionados",
    "¿Hay fotos pendientes de revisión?",
    "¿Qué candidatos llegaron por foto?",
  ];
  $("#sugerencias").innerHTML = SUGERENCIAS.map((s) => `<button type="button">${esc(s)}</button>`).join("");
  $("#sugerencias").addEventListener("click", (e) => {
    if (e.target.tagName === "BUTTON") { $("#pregunta").value = e.target.textContent; $("#formChat").requestSubmit(); }
  });

  function formato(texto) {
    // Markdown mínimo y seguro: negritas, listas y párrafos.
    const lineas = esc(texto).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").split("\n");
    let html = "", lista = null;
    for (const l of lineas) {
      const m = l.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
      if (m) { if (!lista) { lista = /^\s*\d/.test(l) ? "ol" : "ul"; html += `<${lista}>`; } html += `<li>${m[1]}</li>`; continue; }
      if (lista) { html += `</${lista}>`; lista = null; }
      if (l.trim()) html += `<p>${l}</p>`;
    }
    return html + (lista ? `</${lista}>` : "");
  }

  function mensaje(clase, html) {
    const div = document.createElement("div");
    div.className = `msg ${clase}`; div.innerHTML = html;
    $("#mensajes").append(div); div.scrollIntoView({ block: "end", behavior: "smooth" });
    return div;
  }

  $("#formChat").addEventListener("submit", async (e) => {
    e.preventDefault();
    const pregunta = $("#pregunta").value.trim();
    if (!pregunta) return;
    $("#pregunta").value = "";
    mensaje("yo", `<p>${esc(pregunta)}</p>`);
    const espera = mensaje("bot pensando", "<p>Consultando los candidatos…</p>");
    $("#btnPreguntar").disabled = true;
    try {
      const r = await api("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pregunta }) });
      espera.className = "msg bot";
      espera.innerHTML = formato(r.respuesta) + (r.modelo ? `<span class="modelo">Respondió: ${esc(r.modelo)}</span>` : "");
    } catch (err) {
      espera.className = "msg error"; espera.innerHTML = `<p>${esc(err.message)}</p>`;
    } finally {
      $("#btnPreguntar").disabled = false; $("#pregunta").focus();
    }
  });
  $("#pregunta").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#formChat").requestSubmit(); }
  });

  // ───────────────────────── Ejecuciones (admin) ─────────────────────────
  const corto = (v) => { const t = JSON.stringify(v ?? {}); return esc(t.length > 400 ? t.slice(0, 400) + "…" : t); };
  const fecha = (t) => esc(String(t || "").replace("T", " ").replace(/\+00:00$/, ""));
  async function cargarEjecuciones() {
    const flujo = $("#filtroFlujo").value;
    try {
      const filas = await api(`/api/ejecuciones?limite=300${flujo ? `&flujo=${encodeURIComponent(flujo)}` : ""}`);
      $("#conteoEjecuciones").textContent = `${filas.length} ejecuciones (las más recientes primero)`;
      $("#filasEjecuciones").innerHTML = filas.map((f) => `<tr>
        <td>${fecha(f.fecha)}</td><td>${esc(f.flujo)}</td><td class="${f.estado === "ok" ? "ok" : "error"}">${esc(f.estado)}</td>
        <td>${esc(f.duracion_ms)}</td><td>${esc(f.usuario)}</td><td class="json">${corto(f.entrada)}</td>
        <td class="json">${f.error ? esc(f.error) : corto(f.resultado)}</td></tr>`).join("");
    } catch (e) {
      $("#conteoEjecuciones").textContent = e.message;
    }
  }
  $("#filtroFlujo").addEventListener("change", cargarEjecuciones);
  $("#btnEjecuciones").addEventListener("click", cargarEjecuciones);
  async function tarea(ruta, boton) {
    boton.disabled = true;
    try {
      const r = await api(ruta, { method: "POST" });
      $("#conteoEjecuciones").textContent = ruta.endsWith("resumen")
        ? `Resumen: ${r.nuevos} candidatos nuevos, ${r.pendientes} fotos pendientes${r.aviso_telegram ? " · enviado por Telegram" : " · Telegram sin configurar"}`
        : `Reintento: ${r.reintentadas} lecturas procesadas, ${r.fallidas} sin respuesta de la IA`;
      setTimeout(cargarEjecuciones, 600);
    } catch (e) {
      $("#conteoEjecuciones").textContent = e.message;
    } finally { boton.disabled = false; }
  }
  $("#btnResumen").addEventListener("click", (e) => tarea("/api/tareas/resumen", e.currentTarget));
  $("#btnReintentar").addEventListener("click", (e) => tarea("/api/tareas/reintentar", e.currentTarget));

  // ───────────────────────── Inicio ─────────────────────────
  (async () => {
    await cargarSesion();
    await comprobar();
    cargarCandidatos();
    setInterval(comprobar, 60000);
  })();
})();
