export type Pair = [number, number];

export interface Grader {
  key: string;
  name: string;
  family: string;
  kind: "execution" | "judge" | "fix" | "combined";
  caught: Pair;
  injected: Pair;
  failedCorrect: Pair;
  unreadable: number;
  costUsd: number | null;
  seconds: number;
  models: string[];
  byMistake: Record<string, Pair>;
}

export interface Injection {
  judge: string;
  trick: string;
  text: string;
  caught: Pair;
  fooled: Pair;
}

export interface Result {
  rows: (string | number | null)[][];
  error: string | null;
}

export interface Version {
  op: string;
  label: string;
  sql: string;
  result: Result;
  verdicts: Record<string, boolean | null>;
}

export interface Data {
  generated: string;
  dataset: { questions: number; cases: number; references: number; equivalents: number; mutants: number; unclear: number };
  bird: { passedWrong: number; wrong: number };
  sample: Record<string, number>;
  graders: Grader[];
  injections: Injection[];
  walkthrough: {
    qid: number;
    db: string;
    question: string;
    evidence: string;
    referenceSql: string;
    referenceNormalized: string;
    referenceResult: Result;
    versions: Version[];
  };
}
