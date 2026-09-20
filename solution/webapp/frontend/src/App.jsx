import React, { useState } from "react";
import ReportView from "./ReportView.jsx";
import ReviewQueue from "./ReviewQueue.jsx";

export default function App() {
  const [tab, setTab] = useState("report");

  return (
    <div style={{ fontFamily: "sans-serif", padding: "16px" }}>
      <h1>SDOC Review App</h1>
      <button onClick={() => setTab("report")}>Report</button>{" "}
      <button onClick={() => setTab("review")}>Review Queue</button>
      <hr />
      {tab === "report" ? <ReportView /> : <ReviewQueue />}
    </div>
  );
}
