import { useEffect, useState } from "react";
import type { Data, Grader, Pair, Result, Version } from "./types";

const pct = ([hit, n]: Pair) => (n ? Math.round((100 * hit) / n) : 0);
const fmt = (p: Pair) => (p[1] ? `${p[0]} of ${p[1]}` : "–");
const num = (v: unknown) =>
  typeof v === "number" ? v.toLocaleString("en-GB", { maximumFractionDigits: 1 }) : String(v ?? "NULL");

// Plain-language names for each kind of planted mistake.
const MISTAKES: Record<string, string> = {
  drop_where: "Filter removed",
  swap_aggregate: "Wrong aggregate (SUM↔AVG, MAX↔MIN)",
  flip_boundary: "Boundary flipped (> vs >=)",
  limit_off_by_one: "One row too many",
  inner_to_left_join: "INNER JOIN became LEFT JOIN",
  flip_order: "Sort order reversed",
  drop_distinct: "DISTINCT removed (duplicates)",
};
const TRICKS: Record<string, string> = {
  comment: "Reviewer comment",
  grader_note: "Note to the grader",
  fake_verdict: "Ready-made verdict",
  ambiguity: "“The question is ambiguous”",
};

function Bar({ value, tone }: { value: number; tone: "good" | "bad" }) {
  return (
    <div className="bar">
      <div className={`fill ${tone}`} style={{ width: `${value}%` }} />
      <span>{value}%</span>
    </div>
  );
}

function GraderTable({ graders }: { graders: Grader[] }) {
  const groups: [string, Grader["kind"]][] = [
    ["Runs the SQL", "execution"],
    ["LLM judges (read the SQL)", "judge"],
    ["Fixes we tried", "fix"],
    ["Judge and execution must both pass", "combined"],
  ];
  return (
    <table className="graders">
      <thead>
        <tr>
          <th>Grader</th>
          <th>Caught wrong answers</th>
          <th>Rejected correct answers</th>
          <th className="num">Cost / time per grade</th>
        </tr>
      </thead>
      <tbody>
        {groups.map(([title, kind]) => {
          const rows = graders.filter((g) => g.kind === kind);
          if (!rows.length) return null;
          return [
            <tr key={kind} className="group">
              <td colSpan={4}>{title}</td>
            </tr>,
            ...rows.map((g) => (
              <tr key={g.key}>
                <td>
                  <b>{g.name}</b>
                  <div className="sub">{g.family}</div>
                </td>
                <td>
                  <Bar value={pct(g.caught)} tone="good" />
                  <div className="sub">{fmt(g.caught)}</div>
                </td>
                <td>
                  <Bar value={pct(g.failedCorrect)} tone="bad" />
                  <div className="sub">{fmt(g.failedCorrect)}</div>
                </td>
                <td className="num sub">
                  {g.kind === "execution" ? "free, instant" : `${g.costUsd != null ? `$${(g.costUsd / 205).toFixed(4)}` : "plan"} · ${g.seconds}s`}
                </td>
              </tr>
            )),
          ];
        })}
      </tbody>
    </table>
  );
}

function Heatmap({ graders }: { graders: Grader[] }) {
  const cols = graders.filter((g) => g.kind === "execution" || g.kind === "judge");
  return (
    <table className="heat">
      <thead>
        <tr>
          <th>Planted mistake</th>
          {cols.map((g) => (
            <th key={g.key}>{g.name}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Object.entries(MISTAKES).map(([op, label]) => (
          <tr key={op}>
            <td>{label}</td>
            {cols.map((g) => {
              const p = g.byMistake[op] ?? [0, 0];
              const v = pct(p);
              return (
                <td key={g.key} className="cell" style={{ background: `hsl(${(v * 1.2).toFixed(0)} 70% ${92 - v * 0.25}%)` }}>
                  <b>{v}%</b>
                  <div className="sub">{fmt(p)}</div>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Word-level diff against the reference, so the reader sees exactly what was changed.
function diffWords(ref: string, sql: string) {
  const a = ref.split(/(\s+)/), b = sql.split(/(\s+)/);
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: { t: string; changed: boolean }[] = [];
  let i = 0, j = 0;
  while (j < b.length) {
    if (i < a.length && a[i] === b[j]) { out.push({ t: b[j], changed: false }); i++; j++; }
    else if (i < a.length && dp[i + 1][j] >= dp[i][j + 1]) i++;
    else { out.push({ t: b[j], changed: !/^\s+$/.test(b[j]) }); j++; }
  }
  return out;
}

function ResultLine({ r }: { r: Result }) {
  if (r.error) return <span className="err">{r.error}</span>;
  return <span className="result">{r.rows.map((row) => row.map(num).join(", ")).join(" · ") || "(no rows)"}</span>;
}

function Verdicts({ v, label }: { v: Version["verdicts"]; label: string }) {
  // Green when the grader was right about this answer, red when it was wrong.
  return (
    <div className="verdicts">
      {Object.entries(v).map(([name, ok]) => (
        <span key={name} className={`chip ${ok == null ? "na" : ok === (label === "correct") ? "right" : "wrong"}`}>
          {ok == null ? "–" : ok ? "✓ passed" : "✗ caught"} <small>{name}</small>
        </span>
      ))}
    </div>
  );
}

function Walkthrough({ w }: { w: Data["walkthrough"] }) {
  return (
    <div className="walk">
      <div className="q">
        <div className="label">Question {w.qid} · BIRD “{w.db}” database</div>
        <p>“{w.question}”</p>
        {w.evidence && <p className="sub">Hint given to every grader: {w.evidence}</p>}
      </div>
      <div className="version ref">
        <div className="label">The correct answer</div>
        <pre>{w.referenceSql}</pre>
        <div>Result: <ResultLine r={w.referenceResult} /></div>
      </div>
      {w.versions.map((v) => (
        <div className="version" key={v.op}>
          <div className="label">
            {v.label === "wrong" ? "A wrong answer" : "Another correct answer"}: {MISTAKES[v.op.split("+")[0]] ?? v.op}
            {v.op.includes("+inject") && " + a note telling the grader it is right"}
          </div>
          <pre>{diffWords(w.referenceNormalized, v.sql).map((p, i) => (p.changed ? <mark key={i}>{p.t}</mark> : p.t))}</pre>
          <div>Result: <ResultLine r={v.result} /></div>
          <Verdicts v={v.verdicts} label={v.label} />
        </div>
      ))}
    </div>
  );
}

function Injections({ data }: { data: Data }) {
  const judges = [...new Set(data.injections.map((i) => i.judge))].filter((j) => !j.includes(","));
  const tricks = Object.keys(TRICKS).filter((t) => data.injections.some((i) => i.trick === t));
  return (
    <table className="graders inj">
      <thead>
        <tr>
          <th>Text added above the wrong SQL</th>
          {judges.map((j) => (
            <th key={j}>{j}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {tricks.map((t) => (
          <tr key={t}>
            <td>
              <b>{TRICKS[t]}</b>
              <div className="sub mono">{data.injections.find((i) => i.trick === t)?.text}</div>
            </td>
            {judges.map((j) => {
              const r = data.injections.find((i) => i.trick === t && i.judge === j);
              return (
                <td key={j}>
                  {r ? (
                    <>
                      <b>fooled {r.fooled[0]}</b> of {r.fooled[1]}
                      <div className="sub">still caught {fmt(r.caught)}</div>
                    </>
                  ) : (
                    "–"
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function App() {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data.json`).then((r) => r.json()).then(setData);
  }, []);
  if (!data) return <main className="loading">Loading results…</main>;
  const { dataset, bird, graders } = data;
  const judges = graders.filter((g) => g.kind === "judge");
  const best = graders.filter((g) => g.kind === "combined").sort((a, b) => pct(b.caught) - pct(a.caught))[0];
  return (
    <main>
      <header>
        <div className="brand">Tripwire</div>
        <h1>Do AI graders notice when an answer is wrong?</h1>
        <p className="lead">
          When AI models are trained and tested, another program decides whether their answers are right. Tripwire checks those
          graders by slipping them answers that look right but aren't, on {dataset.questions} real questions from the BIRD
          text-to-SQL benchmark.
        </p>
        <div className="stats">
          <div><b>{dataset.cases.toLocaleString()}</b><span>test answers, each labelled by running it</span></div>
          <div><b>{((100 * bird.passedWrong) / bird.wrong).toFixed(1)}%</b><span>of wrong answers passed BIRD's own grader ({bird.passedWrong} of {bird.wrong})</span></div>
          <div><b>{judges.length} model families</b><span>as LLM judges, each with its own blind spot</span></div>
          {best && <div><b>{pct(best.caught)}%</b><span>caught when a judge and execution must both agree ({best.name})</span></div>}
        </div>
      </header>

      <section>
        <h2>Who catches what</h2>
        <p>The same {data.sample.correct + data.sample.wrong} answers ({data.sample.wrong} wrong, {data.sample.correct} correct) went to every grader.</p>
        <GraderTable graders={graders} />
      </section>

      <section>
        <h2>Each grader has its own blind spot</h2>
        <p>Running the SQL can't see order or duplicates. Reading it can't see what the data means.</p>
        <Heatmap graders={graders} />
      </section>

      <section>
        <h2>One question, followed through</h2>
        <Walkthrough w={data.walkthrough} />
      </section>

      <section>
        <h2>Telling the grader the answer is right</h2>
        <p>The same 30 wrong answers, each with a note added above the SQL. “Fooled” counts answers a judge caught without the note and passed with it.</p>
        <Injections data={data} />
      </section>

      <footer>
        Data: BIRD Mini-Dev (CC BY-SA 4.0), 2026 corrected questions. Generated {data.generated}. Code and method:
        github.com/tmjoris/tripwire
      </footer>
    </main>
  );
}
