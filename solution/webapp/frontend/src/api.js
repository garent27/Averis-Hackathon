const BASE = "http://localhost:8001";

export async function getReport() {
  const r = await fetch(`${BASE}/api/report`);
  return r.json();
}

export async function getReviewQueue() {
  const r = await fetch(`${BASE}/api/review`);
  return r.json();
}

export async function saveReview(emailId, siValues, blValues, note) {
  const r = await fetch(`${BASE}/api/review/${emailId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ si_values: siValues, bl_values: blValues, note }),
  });
  return r.json();
}

export async function retry(emailId) {
  const r = await fetch(`${BASE}/api/retry/${emailId}`, { method: "POST" });
  return r.json();
}
