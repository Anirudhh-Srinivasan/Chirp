/* The API URL is configurable in index.html; no framework or build step needed. */
const API_BASE = document
  .querySelector('meta[name="api-base"]')
  .content.replace(/\/$/, "");
const $ = (id) => document.getElementById(id);
let token = null;
let currentUser = null;
let feed = [];
let hasMore = false;
let loadingFeed = false;
let posting = false;
let sessionVersion = 0;
let view = { kind: "latest" };
let viewVersion = 0;
let people = [];
let nextUserBefore = null;
let nextPostBefore = null;

try {
  token = localStorage.getItem("chirp_token");
} catch {
  /* Private browser storage may be blocked. */
}

function message(id, text, error = true) {
  const element = $(id);
  element.textContent = text;
  element.hidden = !text;
  if (id === "notice") element.classList.toggle("error", error);
}

function saveToken(value) {
  token = value;
  try {
    if (value) localStorage.setItem("chirp_token", value);
    else localStorage.removeItem("chirp_token");
  } catch {
    /* The session still works in memory if storage is unavailable. */
  }
}

async function api(path, { method = "GET", body } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error(
      "Can’t reach the server. Check your connection and that the backend is running.",
    );
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) {
      logout(false);
      message("notice", "Your session expired. Please log in again.");
    }
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join(" · ")
      : data.detail;
    throw new Error(
      detail || `Something went wrong (${response.status}). Please try again.`,
    );
  }
  return data;
}

function showSession() {
  const loggedIn = Boolean(currentUser);
  $("authSection").hidden = loggedIn;
  $("feedSection").hidden = !loggedIn;
  $("account").hidden = !loggedIn;
  if (loggedIn) {
    $("accountName").href = `#profile/${currentUser.id}`;
    $("myProfileLink").href = `#profile/${currentUser.id}`;
    $("accountName").textContent = `@${currentUser.username}`;
    $("accountAvatar").textContent = currentUser.username
      .slice(0, 2)
      .toUpperCase();
    $("composerAvatar").textContent = currentUser.username
      .slice(0, 2)
      .toUpperCase();
  }
}

function logout(announce = true) {
  sessionVersion += 1; // Ignore in-flight feed requests from an older session.
  saveToken(null);
  currentUser = null;
  feed = [];
  viewVersion += 1;
  people = [];
  $("userResults").replaceChildren();
  $("profileCard").hidden = true;
  loadingFeed = false;
  $("posts").replaceChildren();
  $("postForm").reset();
  $("loginForm").reset();
  $("signupForm").reset();
  updateCounter();
  showSession();
  if (announce) message("notice", "You’ve logged out. See you soon!", false);
}

function selectTab(signup) {
  $("loginForm").hidden = signup;
  $("signupForm").hidden = !signup;
  for (const [id, selected] of [
    ["loginTab", !signup],
    ["signupTab", signup],
  ]) {
    $(id).setAttribute("aria-selected", String(selected));
    $(id).tabIndex = selected ? 0 : -1;
  }
  message("loginError", "");
  message("signupError", "");
}
$("loginTab").addEventListener("click", () => selectTab(false));
$("signupTab").addEventListener("click", () => selectTab(true));
document.querySelector(".auth-tabs").addEventListener("keydown", (event) => {
  if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const signup =
      event.key === "End" || (event.key !== "Home" && $("signupForm").hidden);
    selectTab(signup);
    $(signup ? "signupTab" : "loginTab").focus();
  }
});

async function authenticate(event, signup) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const errorId = signup ? "signupError" : "loginError";
  const username = $(signup ? "newUsername" : "username").value.trim();
  const password = $(signup ? "newPassword" : "password").value;
  message(errorId, "");
  message("notice", "");
  button.disabled = true;
  let registered = false;
  try {
    if (signup) {
      await api("/signup", {
        method: "POST",
        body: { username, email: $("email").value.trim(), password },
      });
      registered = true;
    }
    const result = await api("/login", {
      method: "POST",
      body: { username, password },
    });
    saveToken(result.access_token);
    currentUser = await api("/me");
    sessionVersion += 1;
    form.reset();
    showSession();
    message(
      "notice",
      signup
        ? "You’re in! Your first chirp is waiting to happen."
        : `Welcome back, @${currentUser.username}.`,
      false,
    );
    await navigate();
  } catch (error) {
    saveToken(null);
    if (registered) {
      selectTab(false);
      $("username").value = username;
      message(
        "loginError",
        `Account created, but automatic login failed. Please log in. ${error.message}`,
      );
    } else message(errorId, error.message);
  } finally {
    button.disabled = false;
  }
}
$("loginForm").addEventListener("submit", (event) =>
  authenticate(event, false),
);
$("signupForm").addEventListener("submit", (event) =>
  authenticate(event, true),
);
$("logoutButton").addEventListener("click", () => logout());

function relativeTime(value) {
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 1000),
  );
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  // All user content uses textContent, never HTML, to avoid stored XSS.
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderPost(post) {
  const article = node("article", "post");
  article.dataset.id = post.id;
  const header = node("div", "post-header");
  const avatar = node("div", "avatar", post.username.slice(0, 2).toUpperCase());
  avatar.setAttribute("aria-hidden", "true");
  const meta = node("div", "post-meta");
  const author = node("a", "post-author", post.username);
  author.href = `#profile/${post.user_id}`;
  meta.append(author, node("div", "post-handle", `@${post.username}`));
  const time = node("time", "", relativeTime(post.created_at));
  time.dateTime = post.created_at;
  time.title = new Date(post.created_at).toLocaleString();
  header.append(avatar, meta, time);
  const actions = node("div", "post-actions");
  const like = node("button", "like-button");
  like.dataset.action = "like";
  like.setAttribute("aria-pressed", String(post.liked_by_me));
  like.setAttribute(
    "aria-label",
    `${post.liked_by_me ? "Unlike" : "Like"} post by ${post.username}, ${post.like_count} likes`,
  );
  like.append(
    node("span", "", post.liked_by_me ? "♥" : "♡"),
    node("span", "", String(post.like_count)),
  );
  actions.append(like);
  if (post.user_id === currentUser?.id) {
    const remove = node("button", "delete-button", "Delete");
    remove.dataset.action = "delete";
    remove.setAttribute("aria-label", "Delete your post");
    actions.append(remove);
  }
  article.append(header, node("p", "post-content", post.content), actions);
  return article;
}

function renderFeed() {
  $("posts").replaceChildren(...feed.map(renderPost));
  $("feedStatus").hidden = feed.length > 0;
  if (!feed.length) {
    $("feedStatus").replaceChildren(
      node(
        "strong",
        "",
        view.kind === "search"
          ? "No matching chirps."
          : "A fresh page. A first thought.",
      ),
      node(
        "span",
        "",
        view.kind === "following"
          ? "Follow someone from their profile to see their chirps here."
          : view.kind === "latest"
            ? "No chirps yet. Start the conversation above."
            : "Try another search or check back later.",
      ),
    );
  }
  $("loadMoreButton").hidden = !hasMore;
}

async function loadFeed(append = false) {
  if (loadingFeed || !currentUser) return;
  const version = sessionVersion;
  const routeVersion = viewVersion;
  loadingFeed = true;
  $("posts").setAttribute("aria-busy", "true");
  $("refreshButton").disabled = true;
  $("loadMoreButton").disabled = true;
  message("feedError", "");
  if (!feed.length) {
    $("feedStatus").hidden = false;
    $("feedStatus").textContent = "Gathering the latest chirps…";
  }
  try {
    const cursor = append && feed.length ? `&before=${feed.at(-1).id}` : "";
    let incoming;
    if (view.kind === "search") {
      const data = await api(
        `/search?q=${encodeURIComponent(view.query)}&limit=20${append && nextPostBefore ? `&post_before=${nextPostBefore}` : ""}`,
      );
      if (version !== sessionVersion || routeVersion !== viewVersion) return;
      incoming = data.posts;
      nextPostBefore = data.next_post_before;
      hasMore = nextPostBefore !== null;
      if (!append) {
        people = data.users;
        nextUserBefore = data.next_user_before;
        renderPeople();
      }
    } else {
      const filter =
        view.kind === "profile" ? `&user_id=${view.id}` : `&feed=${view.kind}`;
      incoming = await api(`/posts?limit=20${cursor}${filter}`);
      if (version !== sessionVersion || routeVersion !== viewVersion) return;
      hasMore = incoming.length === 20;
    }
    feed = append
      ? [
          ...feed,
          ...incoming.filter((post) => !feed.some((old) => old.id === post.id)),
        ]
      : incoming;
    renderFeed();
  } catch (error) {
    if (version === sessionVersion && routeVersion === viewVersion) {
      message("feedError", error.message);
      if (!feed.length)
        $("feedStatus").textContent =
          "Couldn’t load the feed. Use Refresh to try again.";
    }
  } finally {
    if (version === sessionVersion && routeVersion === viewVersion) {
      loadingFeed = false;
      $("posts").setAttribute("aria-busy", "false");
      $("refreshButton").disabled = false;
      $("loadMoreButton").disabled = false;
    }
  }
}

function updateCounter() {
  const length = Array.from($("postContent").value).length;
  $("characterCount").textContent = `${length} / 280`;
  $("postButton").disabled =
    posting || !$("postContent").value.trim() || length > 280;
}
$("postContent").addEventListener("input", updateCounter);
$("postForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = $("postContent").value.trim();
  if (!content || posting) return;
  const version = sessionVersion;
  posting = true;
  $("postContent").readOnly = true;
  $("postButton").disabled = true;
  message("postError", "");
  try {
    const post = await api("/posts", { method: "POST", body: { content } });
    if (version !== sessionVersion) return;
    // Insert the server's persisted result immediately, without reloading the page.
    // Own posts do not belong in Following, which strictly contains followed users.
    if (view.kind === "latest") {
      feed = [post, ...feed.filter((item) => item.id !== post.id)];
      renderFeed();
    }
    $("postForm").reset();
    message("notice", "Your chirp is out in the world.", false);
  } catch (error) {
    if (version === sessionVersion) message("postError", error.message);
  } finally {
    posting = false;
    $("postContent").readOnly = false;
    updateCounter();
  }
});

function confirmDelete() {
  const dialog = $("deleteDialog");
  return new Promise((resolve) => {
    dialog.returnValue = "cancel";
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "delete"),
      { once: true },
    );
    dialog.showModal();
  });
}
$("posts").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const id = Number(button.closest(".post").dataset.id);
  const version = sessionVersion;
  button.disabled = true;
  try {
    if (button.dataset.action === "delete") {
      if (!(await confirmDelete())) return;
      if (version !== sessionVersion) return;
      await api(`/posts/${id}`, { method: "DELETE" });
      if (version !== sessionVersion) return;
      feed = feed.filter((post) => post.id !== id);
      message("notice", "Chirp deleted.", false);
    } else {
      const updated = await api(`/posts/${id}/like`, { method: "POST" });
      if (version !== sessionVersion) return;
      feed = feed.map((post) => (post.id === id ? updated : post));
    }
    renderFeed();
  } catch (error) {
    message("notice", error.message);
  } finally {
    button.disabled = false;
  }
});
$("refreshButton").addEventListener("click", () => navigate());
$("loadMoreButton").addEventListener("click", () => loadFeed(true));
setInterval(() => {
  document.querySelectorAll(".post time").forEach((time) => {
    time.textContent = relativeTime(time.dateTime);
  });
}, 30000);
window.addEventListener("storage", (event) => {
  if (event.key === "chirp_token" && event.newValue !== token) {
    logout(false);
    message(
      "notice",
      "Your account session changed in another tab. Please log in again.",
    );
  }
});

async function initialize() {
  if (!token) {
    showSession();
    return;
  }
  $("authSection").hidden = true;
  message("notice", "Restoring your session…", false);
  try {
    currentUser = await api("/me");
    showSession();
    message("notice", "");
    await navigate();
  } catch (error) {
    // A network outage should not destroy a potentially valid saved token.
    showSession();
    message("notice", error.message);
  }
}
function renderPeople() {
  $("userResults").replaceChildren();
  if (people.length)
    $("userResults").append(node("h3", "results-heading", "People"));
  for (const person of people) {
    const link = node("a", "person-card", `@${person.username} →`);
    link.href = `#profile/${person.id}`;
    $("userResults").append(link);
  }
  $("moreUsersButton").hidden = nextUserBefore === null;
}

function renderProfile(profile) {
  const card = $("profileCard");
  card.replaceChildren(
    node("div", "avatar", profile.username.slice(0, 2).toUpperCase()),
    node("h2", "", `@${profile.username}`),
    node(
      "p",
      "muted",
      profile.joined_at
        ? `Joined ${new Date(profile.joined_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}`
        : "Joined before signup dates were recorded",
    ),
  );
  const counts = node("div", "profile-counts");
  for (const [direction, count] of [
    ["followers", profile.follower_count],
    ["following", profile.following_count],
  ]) {
    const link = node("a", "", `${count} ${direction}`);
    link.href = `#${direction}/${profile.id}`;
    counts.append(link);
  }
  card.append(counts);
  if (profile.id !== currentUser.id) {
    const button = node(
      "button",
      profile.followed_by_me ? "secondary" : "primary",
      profile.followed_by_me ? "Unfollow" : "Follow",
    );
    button.id = "followButton";
    button.setAttribute("aria-pressed", String(profile.followed_by_me));
    button.addEventListener("click", async () => {
      button.disabled = true;
      const routeVersion = viewVersion;
      try {
        const updated = await api(`/users/${profile.id}/follow`, {
          method: profile.followed_by_me ? "DELETE" : "POST",
        });
        if (routeVersion === viewVersion && currentUser) renderProfile(updated);
      } catch (error) {
        message("notice", error.message);
      } finally {
        button.disabled = false;
      }
    });
    card.append(button);
  } else card.append(node("span", "pill", "YOUR PROFILE"));
}

async function loadConnections(append = false) {
  const version = viewVersion;
  $("moreUsersButton").disabled = true;
  try {
    const data = await api(
      `/users/${view.id}/${view.kind}?limit=20${append && nextUserBefore ? `&before=${nextUserBefore}` : ""}`,
    );
    if (version !== viewVersion || !currentUser) return;
    people = append ? [...people, ...data] : data;
    nextUserBefore = data.length === 20 ? data.at(-1).id : null;
    renderPeople();
    $("feedStatus").hidden = people.length > 0;
    $("feedStatus").textContent = `No ${view.kind} yet.`;
  } catch (error) {
    if (version === viewVersion) message("feedError", error.message);
  } finally {
    if (version === viewVersion) $("moreUsersButton").disabled = false;
  }
}

async function navigate() {
  if (!currentUser) return;
  const hash = location.hash.slice(1);
  const match = /^(profile|followers|following)\/(\d+)$/.exec(hash);
  let query = "";
  try {
    if (hash.startsWith("search/"))
      query = decodeURIComponent(hash.slice(7)).trim().slice(0, 100);
  } catch {
    /* Malformed bookmarks fall back to Latest. */
  }
  view = match
    ? { kind: match[1], id: Number(match[2]) }
    : query
      ? { kind: "search", query }
      : { kind: hash === "following" ? "following" : "latest" };
  const version = ++viewVersion;
  // Invalidate stale responses when navigating rapidly between tabs/profiles/search.
  loadingFeed = false;
  feed = [];
  people = [];
  hasMore = false;
  nextUserBefore = nextPostBefore = null;
  $("posts").replaceChildren();
  $("userResults").replaceChildren();
  $("moreUsersButton").hidden = true;
  $("moreUsersButton").disabled = false;
  $("loadMoreButton").hidden = true;
  $("profileCard").hidden = true;
  $("postForm").hidden = !["latest", "following"].includes(view.kind);
  message("feedError", "");
  $("searchInput").value = query;
  for (const kind of ["latest", "following"]) {
    $(kind + "Tab").removeAttribute("aria-current");
    if (view.kind === kind)
      $(kind + "Tab").setAttribute("aria-current", "page");
  }
  $("viewTitle").textContent =
    view.kind === "search"
      ? `Search: ${query}`
      : view.kind[0].toUpperCase() + view.kind.slice(1);
  $("viewDescription").textContent =
    view.kind === "following"
      ? "Chirps from people you follow"
      : view.kind === "latest"
        ? "The latest from everyone"
        : "Explore the conversation";
  $("feedStatus").hidden = false;
  $("feedStatus").textContent = "Loading…";
  if (["profile", "followers", "following"].includes(view.kind) && view.id) {
    try {
      const profile = await api(`/users/${view.id}`);
      if (version !== viewVersion || !currentUser) return;
      renderProfile(profile);
      $("profileCard").hidden = false;
      $("viewTitle").textContent =
        view.kind === "profile"
          ? `Chirps by @${profile.username}`
          : `${view.kind} · @${profile.username}`;
    } catch (error) {
      if (version === viewVersion) {
        message("feedError", error.message);
        $("feedStatus").hidden = true;
      }
      return;
    }
  }
  if (view.id && view.kind !== "profile") {
    $("loadMoreButton").hidden = true;
    await loadConnections();
  } else await loadFeed();
}

$("searchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = $("searchInput").value.trim();
  if (!query) return;
  const hash = `#search/${encodeURIComponent(query)}`;
  if (location.hash === hash) navigate();
  else location.hash = hash;
});
$("moreUsersButton").addEventListener("click", async () => {
  if (view.kind !== "search") {
    await loadConnections(true);
    return;
  }
  const version = viewVersion;
  $("moreUsersButton").disabled = true;
  try {
    const data = await api(
      `/search?q=${encodeURIComponent(view.query)}&limit=20&user_before=${nextUserBefore}`,
    );
    if (version !== viewVersion || !currentUser) return;
    people.push(...data.users);
    nextUserBefore = data.next_user_before;
    renderPeople();
  } catch (error) {
    if (version === viewVersion) message("feedError", error.message);
  } finally {
    if (version === viewVersion) $("moreUsersButton").disabled = false;
  }
});
window.addEventListener("hashchange", navigate);
initialize();
