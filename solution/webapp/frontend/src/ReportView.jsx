import React, { useEffect, useState } from "react";
import { getReport, retry } from "./api";

export default function ReportView() {
  const [rows, setRows] = useState([]);

  function load() {
    getReport().then(setRows);
  }

  useEffect(load, []);

  async function handleRetry(emailId) {
    await retry(emailId);
    load();
  }

  return (
    <div>
      <h2>Report</h2>
      <button onClick={load}>Refresh</button>
      <table border="1" cellPadding="4">
        <thead>
          <tr>
            <th>email_id</th>
            <th>category</th>
            <th>status</th>
            <th>has_defect</th>
            <th>flagged fields (SI / BL)</th>
            <th>error</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.email_id}>
              <td>{row.email_id}</td>
              <td>{row.category}</td>
              <td>{row.status}</td>
              <td>{row.has_defect ? "yes" : "no"}</td>
              <td>
                {row.defect_fields && row.defect_fields.length > 0 ? (
                  <ul>
                    {row.defect_fields.map((f) => (
                      <li key={f}>
                        <b>{f}</b>: SI = {String(row.si_values?.[f])} / BL ={" "}
                        {String(row.bl_values?.[f])}
                      </li>
                    ))}
                  </ul>
                ) : (
                  "-"
                )}
              </td>
              <td>{row.error || ""}</td>
              <td>
                {row.status === "FAILED" && (
                  <button onClick={() => handleRetry(row.email_id)}>Retry</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
