"use client";

import { useState } from "react";
import {
  createStory,
  ingestStory,
  getOptions,
  chooseOption,
  getPath,
  type StoryBible,
  type Option,
} from "@/lib/api";

type Step = "input" | "analyzing" | "reading";

interface HistoryEntry {
  nodeId: string;
  label: string;
}

const APPROACH_COLORS: Record<string, string> = {
  ESCALATE: "border-red-500/40 hover:bg-red-500/10",
  REVEAL: "border-amber-500/40 hover:bg-amber-500/10",
  QUIET: "border-blue-500/40 hover:bg-blue-500/10",
  REVERSAL: "border-purple-500/40 hover:bg-purple-500/10",
};

export default function Home() {
  const [step, setStep] = useState<Step>("input");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [bible, setBible] = useState<StoryBible | null>(null);
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [pathText, setPathText] = useState("");
  const [options, setOptions] = useState<Option[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  async function refresh(nodeId: string) {
    const [path, opts] = await Promise.all([getPath(nodeId), getOptions(nodeId)]);
    setPathText(path.text);
    setOptions(opts);
  }

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStep("analyzing");
    try {
      const story = await createStory(title, text);
      const { story: updated, root_node_id } = await ingestStory(story.id);
      setBible(updated.bible_json);
      setCurrentNodeId(root_node_id);
      setHistory([{ nodeId: root_node_id, label: "Start" }]);
      await refresh(root_node_id);
      setStep("reading");
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : String(err));
      setStep("input");
    }
  }

  async function handleChoose(option: Option) {
    if (!currentNodeId) return;
    setError(null);
    setBusy(true);
    try {
      const node = await chooseOption(currentNodeId, option.id);
      setCurrentNodeId(node.id);
      setHistory((h) => [...h, { nodeId: node.id, label: option.title }]);
      await refresh(node.id);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRewind(entry: HistoryEntry, index: number) {
    setError(null);
    setBusy(true);
    try {
      setCurrentNodeId(entry.nodeId);
      setHistory((h) => h.slice(0, index + 1));
      await refresh(entry.nodeId);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Story Continuation
        </h1>

        {error && (
          <p className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        )}

        {step === "input" && (
          <form onSubmit={handleAnalyze} className="flex flex-col gap-4">
            <input
              type="text"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="rounded border border-black/10 bg-white px-3 py-2 text-black dark:border-white/20 dark:bg-zinc-900 dark:text-zinc-50"
            />
            <textarea
              placeholder="Paste an incomplete story..."
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
              rows={12}
              className="rounded border border-black/10 bg-white px-3 py-2 text-black dark:border-white/20 dark:bg-zinc-900 dark:text-zinc-50"
            />
            <button
              type="submit"
              className="rounded-full bg-foreground px-5 py-3 font-medium text-background transition-colors hover:bg-[#383838] dark:hover:bg-[#ccc]"
            >
              Analyze &amp; Begin
            </button>
          </form>
        )}

        {step === "analyzing" && (
          <p className="text-zinc-600 dark:text-zinc-400">
            Analyzing story and building the story bible... this calls the AI once and can take a few seconds.
          </p>
        )}

        {step === "reading" && (
          <div className="flex flex-col gap-6">
            {bible && (
              <div className="flex flex-wrap gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                {bible.pov && (
                  <span className="rounded-full border border-black/10 px-2 py-1 dark:border-white/20">
                    POV: {bible.pov}
                  </span>
                )}
                {bible.characters?.map((c) => (
                  <span
                    key={c.name}
                    className="rounded-full border border-black/10 px-2 py-1 dark:border-white/20"
                  >
                    {c.name} ({c.role})
                  </span>
                ))}
              </div>
            )}

            {history.length > 1 && (
              <div className="flex flex-wrap items-center gap-1 text-xs text-zinc-500">
                <span>Rewind:</span>
                {history.map((h, i) => (
                  <button
                    key={h.nodeId}
                    onClick={() => handleRewind(h, i)}
                    disabled={busy || h.nodeId === currentNodeId}
                    className="rounded-full border border-black/10 px-2 py-1 hover:bg-black/5 disabled:opacity-40 dark:border-white/20 dark:hover:bg-white/10"
                  >
                    {h.label}
                  </button>
                ))}
              </div>
            )}

            <div className="whitespace-pre-wrap rounded border border-black/10 bg-white p-4 leading-relaxed text-black dark:border-white/20 dark:bg-zinc-900 dark:text-zinc-50">
              {pathText}
            </div>

            <div className="flex flex-col gap-3">
              <h2 className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
                What happens next?
              </h2>
              {busy && <p className="text-sm text-zinc-500">Writing continuation...</p>}
              <div className="grid gap-3 sm:grid-cols-1">
                {options.map((opt) => (
                  <button
                    key={opt.id}
                    onClick={() => handleChoose(opt)}
                    disabled={busy}
                    className={`rounded border bg-white px-4 py-3 text-left transition-colors disabled:opacity-40 dark:bg-zinc-900 ${
                      APPROACH_COLORS[opt.approach_type] ?? "border-black/10 dark:border-white/20"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-black/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500 dark:bg-white/10">
                        {opt.approach_type}
                      </span>
                      <span className="font-medium text-black dark:text-zinc-50">{opt.title}</span>
                    </div>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{opt.pitch}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
