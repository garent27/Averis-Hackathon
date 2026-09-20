import React, { useEffect, useState } from "react";
import { getReviewQueue, saveReview, retry } from "./api";

const FIELDS = [
  "shipper", "consignee", "notify_party",
  "port_of_loading", "port_of_discharge",
  "container_count", "gross_weight_kg",
];

function ReviewItem({ item, onSaved }) {
  const [si, setSi] = useState(() => ({ ...(item.si_values || {}) }));
  const [bl, setBl] = useState(() => ({ ...(item.bl_values || {}) }));
  const [note, setNote] = useState("");

  async function handleSave() {
    await saveReview(item.email_id, si, bl, note);
    onSaved();
  }

  async function handleRetry() {
    await retry(item.email_id);
    onSaved();
  }

  return (
    <div style={{ border: "1px solid black", padding: "8px", marginBottom: "12px" }}>
      <h3>{item.email_id}</h3>
      <p>
        <b>Reason:</b> {item.review_reason || item.error || "unknown"}
      </p>
      <p>
        <b>Subject:</b> {item.subject}
      </p>
      <p>
        <b>From:</b> {item.from}
      </p>
      <p>
        <b>Attachments (evidence):</b> {(item.attachments || []).join(", ") || "none"}
      </p>

      <table border="1" cellPadding="4">
        <thead>
          <tr>
            <th>field</th>
            <th>SI value</th>
            <th>BL value</th>
          </tr>
        </thead>
        <tbody>
          {FIELDS.map((f) => (
            <tr key={f}>
              <td>{f}</td>
              <td>
                <input
                  value={si[f] ?? ""}
                  onChange={(e) => setSi({ ...si, [f]: e.target.value })}
                />
              </td>
              <td>
                <input
                  value={bl[f] ?? ""}
                  onChange={(e) => setBl({ ...bl, [f]: e.target.value })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p>
        <label>
          Note: <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </p>

      <button onClick={handleSave}>Save</button>{" "}
      <button onClick={handleRetry}>Retry extraction</button>
    </div>
  );
}

export default function ReviewQueue() {
  const [items, setItems] = useState([]);

  function load() {
    getReviewQueue().then(setItems);
  }

  useEffect(load, []);

  return (
    <div>
      <h2>Review Queue ({items.length})</h2>
      <button onClick={load}>Refresh</button>
      {items.length === 0 && <p>Nothing needs review right now.</p>}
      {items.map((item) => (
        <ReviewItem key={item.email_id} item={item} onSaved={load} />
      ))}
    </div>
  );
}
