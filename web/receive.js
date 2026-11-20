(function () {
  "use strict";

  function $id(s) { return document.getElementById(s); }

  var toastEl = $id("toast"), toastTmr = 0;
  function toast(text, ok) {
    toastEl.textContent = text;
    toastEl.className = "show" + (ok ? " ok" : " bad");
    clearTimeout(toastTmr);
    toastTmr = setTimeout(function () { toastEl.className = ""; }, 3000);
  }

  function mb(b) { return Math.round(b / 1048576) + "MB"; }

  var remainBytes = null;

  function handle401() {
    toast("需要密码", false);
    setTimeout(function () { location.reload(); }, 1000);
  }

  function boot() {
    fetch("/api/meta", { credentials: "same-origin" }).then(function (r) {
      if (r.status === 401) { handle401(); return Promise.reject(); }
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (meta) {
      if (meta.need_password && !meta.authed) {
        $id("main").style.display = "none";
        $id("gate").style.display = "";
      } else {
        enter(meta);
      }
    }).catch(function () {});
  }

  function login() {
    var pwd = $id("gateInput").value;
    fetch("/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd })
    }).then(function (r) {
      if (r.status === 401) { handle401(); return; }
      if (!r.ok) { $id("gateErr").textContent = "密码错误"; return; }
      boot();
    }).catch(function () { $id("gateErr").textContent = "网络错误"; });
  }

  function fmtTime(s) {
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h > 0 ? h + ":" : "") + (m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  function enter(meta) {
    $id("main").style.display = "";
    $id("gate").style.display = "none";
    $id("brandText").textContent = meta.title || "";
    $id("footLeft").textContent = (meta.receive && meta.receive.limit_text) || "";
    if (meta.receive && typeof meta.receive.quota === "object" && typeof meta.receive.quota.remaining === "number") {
      remainBytes = meta.receive.quota.remaining;
    }

    if (typeof meta.expires_in === "number" && meta.expires_in < 0) {
      $id("footRight").textContent = "不限时";
    } else if (typeof meta.expires_in === "number" && meta.expires_in > 0) {
      var left = meta.expires_in | 0;
      (function tick() {
        $id("footRight").textContent = fmtTime(left);
        if (left <= 0) return;
        left--;
        setTimeout(tick, 1000);
      })();
    }

    if (!meta.allow_upload) $id("drop").style.display = "none";
    bindDrop();
  }

  function bindDrop() {
    var d = $id("drop");
    ["dragenter", "dragover"].forEach(function (ev) {
      d.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); d.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      d.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); d.classList.remove("over"); });
    });
    d.addEventListener("drop", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var fl = e.dataTransfer.files;
      if (fl && fl.length) send(Array.prototype.slice.call(fl));
    });
    $id("pickBtn").addEventListener("click", function () { $id("fileInput").click(); });
    $id("fileInput").addEventListener("change", function () {
      if (this.files.length) send(Array.prototype.slice.call(this.files));
      this.value = "";
    });
  }

  function send(files) {
    var i = 0;
    (function next() {
      if (i >= files.length) return;
      var f = files[i++];
      uploadOne(f).catch(function () {}).then(next);
    })();
  }

  function row(file) {
    var div = document.createElement("div");
    div.className = "item";
    div.innerHTML = '<div class="info"><div class="name"></div><div class="meta"></div><div class="bar"><i></i></div></div><div class="state">等待</div>';
    $id("list").insertBefore(div, $id("list").firstChild);
    return {
      row: div,
      nameEl: div.querySelector(".name"),
      metaEl: div.querySelector(".meta"),
      barEl: div.querySelector(".bar i"),
      stateEl: div.querySelector(".state")
    };
  }

  function xhrChunk(uid, idx, blob, onProgress) {
    return new Promise(function (resolve, reject) {
      var x = new XMLHttpRequest();
      x.open("POST", "/api/upload/chunk");
      x.setRequestHeader("X-Upload-Id", uid);
      x.setRequestHeader("X-Chunk-Index", String(idx));
      if (onProgress) x.onprogress = onProgress;
      x.onload = function () {
        if (x.status === 401) { handle401(); reject(new Error("401")); }
        else if (x.status >= 200 && x.status < 300) resolve(x);
        else reject(new Error("chunk " + x.status));
      };
      x.onerror = function () { reject(new Error("network")); };
      x.send(blob);
    });
  }

  function uploadOne(file) {
    var refs = row(file);
    refs.nameEl.textContent = file.name;
    refs.metaEl.textContent = mb(file.size);
    refs.barEl.style.width = "0%";
    refs.stateEl.textContent = "0%";

    return fetch("/api/upload/begin", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file.name, total: file.size })
    }).then(function (r) {
      if (r.status === 413) {
        refs.stateEl.textContent = "失败";
        refs.stateEl.className = "state bad";
        toast("超过接收总量", false);
        return false;
      }
      if (r.status === 401) { handle401(); return Promise.reject(new Error("401")); }
      if (!r.ok) return Promise.reject(new Error("begin " + r.status));
      return r.json().then(function (data) {
        var uid = data.upload_id;
        var cs = data.chunk_size;
        var total = Math.max(1, Math.ceil(file.size / cs));

        function sendChunk(idx) {
          if (idx >= total) {
            return fetch("/api/upload/finish", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ upload_id: uid })
            }).then(function (fr) {
              if (fr.status === 401) { handle401(); return; }
              if (!fr.ok) throw new Error("finish " + fr.status);
              refs.stateEl.textContent = "已完成";
              refs.stateEl.className = "state ok";
              refs.barEl.style.width = "100%";
              if (typeof remainBytes === "number") {
                remainBytes -= file.size;
                $id("footLeft").textContent = "剩余 " + mb(remainBytes);
              }
            });
          }
          var s = idx * cs;
          var e = Math.min(s + cs, file.size);
          var chunk = file.slice(s, e);
          return xhrChunk(uid, idx, chunk, function (pe) {
            if (pe.lengthComputable) {
              var overall = (idx + pe.loaded / pe.total) / total;
              var p = Math.min(100, Math.round(overall * 100));
              refs.barEl.style.width = p + "%";
              refs.stateEl.textContent = p + "%";
            }
          }).then(function () { return sendChunk(idx + 1); });
        }

        return sendChunk(0);
      });
    }).then(function (v) {
      return v;
    }).catch(function (e) {
      if (e.message !== "401") {
        refs.stateEl.textContent = "失败";
        refs.stateEl.className = "state bad";
      }
      return false;
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
