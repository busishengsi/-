const Api = {
  token() {
    return localStorage.getItem("token") || "";
  },
  async request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (this.token()) headers.set("Authorization", `Bearer ${this.token()}`);
    if (options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
      options.body = JSON.stringify(options.body);
    }
    const response = await fetch(path, {...options, headers});
    const result = await response.json().catch(() => ({message: "服务器返回格式错误"}));
    if (!response.ok || result.code !== 0) throw new Error(result.message || "请求失败");
    return result.data;
  }
};

const labels = {
  type: {lost: "寻找物品", found: "捡到物品"},
  category: {digital: "数码产品", card: "证件卡类", daily: "生活用品", other: "其他"},
  audit: {pending: "待审核", approved: "已通过", rejected: "已驳回"},
  auditClass: {pending: "pending", approved: "pass", rejected: "reject"}
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}

function showError(error) {
  alert(error.message || "操作失败，请稍后重试");
}

function requireLogin() {
  if (!Api.token()) {
    location.href = "login.html";
    return false;
  }
  return true;
}

function itemCard(item) {
  const element = document.createElement("article");
  element.className = "item-card";
  element.tabIndex = 0;
  element.innerHTML = `
    <span class="status-tag ${labels.auditClass[item.audit_status]}">${labels.audit[item.audit_status]}</span>
    <h3>${escapeHtml(item.title)}</h3>
    <p class="item-category">物品分类：${labels.category[item.category] || "其他"}</p>
    <p class="item-desc">留言：${escapeHtml(item.description || "暂无描述")}</p>
    <p class="item-contact">联系：${escapeHtml(item.contact || "未填写")}</p>
    <p class="item-type">信息类型：${labels.type[item.type]}</p>`;
  element.onclick = () => location.href = `detail.html?id=${item.id}`;
  element.onkeydown = event => {
    if (event.key === "Enter") element.click();
  };
  return element;
}

async function loadCards(keyword = "", limit = 100) {
  const query = new URLSearchParams({page_size: String(limit)});
  if (keyword) query.set("keyword", keyword);
  const data = await Api.request(`/api/items?${query}`);
  const container = document.getElementById("cardContainer");
  container.innerHTML = "";
  data.items.forEach(item => container.appendChild(itemCard(item)));
  if (!data.items.length) container.innerHTML = "<p>暂时没有已通过审核的信息。</p>";
}

function bindPreview() {
  const uploadBox = document.getElementById("uploadBox");
  const input = document.getElementById("imgFile");
  const preview = document.getElementById("img-preview");
  if (!uploadBox || !input) return;
  uploadBox.onclick = event => {
    if (event.target !== input) input.click();
  };
  input.onchange = () => {
    if (!input.files[0] || !preview) return;
    preview.src = URL.createObjectURL(input.files[0]);
    preview.style.display = "block";
  };
}

async function recognizeSelectedImage() {
  const input = document.getElementById("imgFile");
  if (!input.files[0]) throw new Error("请先选择图片");
  const form = new FormData();
  form.append("image", input.files[0]);
  return Api.request("/api/ai/recognize", {method: "POST", body: form});
}

async function initIndex() {
  bindPreview();
  await loadCards("", 6);
  document.getElementById("aiBtn").onclick = async () => {
    try {
      const result = await recognizeSelectedImage();
      alert(`识别结果：${result.title}\n分类：${result.category_label}\n置信度：${Math.round(result.confidence * 100)}%`);
    } catch (error) { showError(error); }
  };
}

async function initList() {
  await loadCards();
  const search = document.getElementById("search-input");
  const button = search.parentElement.querySelector("button");
  const run = () => loadCards(search.value.trim()).catch(showError);
  button.onclick = run;
  search.onkeydown = event => { if (event.key === "Enter") run(); };
}

async function initDetail() {
  const itemId = new URLSearchParams(location.search).get("id");
  if (!itemId) throw new Error("缺少物品编号");
  const item = await Api.request(`/api/items/${itemId}`);
  document.getElementById("itemTitle").textContent = item.title;
  document.getElementById("itemType").textContent = labels.type[item.type];
  document.getElementById("itemCategory").textContent = labels.category[item.category] || "其他";
  document.getElementById("itemDesc").textContent = item.description || "暂无描述";
  document.getElementById("itemContact").textContent = item.contact || "未填写";
  const tag = document.getElementById("statusTag");
  tag.textContent = labels.audit[item.audit_status];
  tag.className = `status-tag ${labels.auditClass[item.audit_status]}`;
}

function initLogin() {
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  document.getElementById("toRegister").onclick = event => {
    event.preventDefault(); loginForm.classList.add("hidden"); registerForm.classList.remove("hidden");
  };
  document.getElementById("toLogin").onclick = event => {
    event.preventDefault(); registerForm.classList.add("hidden"); loginForm.classList.remove("hidden");
  };
  document.getElementById("loginBtn").onclick = async () => {
    const inputs = loginForm.querySelectorAll("input");
    try {
      const data = await Api.request("/api/auth/login", {
        method: "POST", body: {username: inputs[0].value.trim(), password: inputs[1].value}
      });
      localStorage.setItem("token", data.token);
      localStorage.setItem("user", JSON.stringify(data.user));
      location.href = data.user.role === "admin" ? "audit.html" : "index.html";
    } catch (error) { showError(error); }
  };
  registerForm.querySelector("button").onclick = async () => {
    const inputs = registerForm.querySelectorAll("input");
    if (inputs[1].value !== inputs[2].value) return showError(new Error("两次输入的密码不一致"));
    try {
      const data = await Api.request("/api/auth/register", {
        method: "POST", body: {username: inputs[0].value.trim(), password: inputs[1].value}
      });
      localStorage.setItem("token", data.token);
      localStorage.setItem("user", JSON.stringify(data.user));
      location.href = "index.html";
    } catch (error) { showError(error); }
  };
}

function initPublish() {
  if (!requireLogin()) return;
  bindPreview();
  let recognizedCategory = "other";
  const input = document.getElementById("imgFile");
  input.addEventListener("change", async () => {
    try {
      const result = await recognizeSelectedImage();
      recognizedCategory = result.category;
      if (!document.getElementById("title").value.trim()) document.getElementById("title").value = result.title;
    } catch (error) { showError(error); }
  });
  document.getElementById("publishForm").onsubmit = async event => {
    event.preventDefault();
    const form = new FormData();
    const selectedType = document.querySelector('input[name="type"]:checked').value;
    form.append("type", selectedType === "捡到物品" ? "found" : "lost");
    form.append("title", document.getElementById("title").value.trim());
    form.append("description", document.getElementById("desc").value.trim());
    form.append("contact", document.getElementById("contact").value.trim());
    form.append("category", recognizedCategory);
    if (input.files[0]) form.append("image", input.files[0]);
    try {
      await Api.request("/api/items", {method: "POST", body: form});
      alert("发布成功，信息已进入审核队列。");
      location.href = "index.html";
    } catch (error) { showError(error); }
  };
}

async function initAudit() {
  if (!requireLogin()) return;
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  if (user.role !== "admin") throw new Error("当前账号没有审核权限");
  const data = await Api.request("/api/admin/items?audit_status=pending");
  const container = document.getElementById("auditList");
  container.innerHTML = "";
  for (const item of data.items) {
    const card = document.createElement("article");
    card.className = "audit-card";
    card.innerHTML = `
      <span class="status-tag pending">待审核</span>
      <h3>${escapeHtml(item.title)}</h3>
      <div class="audit-info">
        <p>类型：${labels.type[item.type]}</p><p>物品分类：${labels.category[item.category] || "其他"}</p>
        <p>留言：${escapeHtml(item.description || "暂无描述")}</p><p>联系方式：${escapeHtml(item.contact || "未填写")}</p>
      </div><div class="btn-group"><button class="btn-pass">通过审核</button><button class="btn-reject">驳回</button></div>`;
    const review = async action => {
      const note = action === "reject" ? prompt("请输入驳回原因", "信息不完整") || "" : "";
      await Api.request(`/api/admin/items/${item.id}/audit`, {method: "PATCH", body: {action, note}});
      card.remove();
    };
    card.querySelector(".btn-pass").onclick = () => review("approve").catch(showError);
    card.querySelector(".btn-reject").onclick = () => review("reject").catch(showError);
    container.appendChild(card);
  }
  if (!data.items.length) container.innerHTML = "<p>当前没有待审核信息。</p>";
}

window.goBack = () => location.href = "list.html";

document.addEventListener("DOMContentLoaded", () => {
  const page = location.pathname.split("/").pop() || "index.html";
  const initializers = {
    "index.html": initIndex, "list.html": initList, "detail.html": initDetail,
    "login.html": initLogin, "publish.html": initPublish, "audit.html": initAudit
  };
  Promise.resolve(initializers[page]?.()).catch(showError);
});
