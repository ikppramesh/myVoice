"use client";
import { useEffect, useState } from "react";

type Voice = { id: string; name: string; language: string; indic_samples: string[] };
type Lang = { code: string; name: string; indian: boolean };
type Job = { status: string; progress: number; message: string; result: { text?: string; model?: string; audio?: string } | null };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body as T;
}

// Start a job on the engine and poll until it finishes.
async function runJob(body: object, onProgress: (j: Job) => void): Promise<Job["result"]> {
  const { id } = await api<{ id: string }>("/api/jobs", { method: "POST", body: JSON.stringify(body) });
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    const job = await api<Job>(`/api/jobs/${id}`);
    onProgress(job);
    if (job.status === "done") return job.result;
    if (job.status === "error") throw new Error(job.message);
  }
}

const looksEnglish = (t: string) => {
  const letters = [...t].filter((c) => /\p{L}/u.test(c));
  return letters.length > 0 && letters.filter((c) => c.charCodeAt(0) < 128).length / letters.length > 0.5;
};

const FAQ = [
  ["Is my voice uploaded anywhere?", "No. Voice cloning runs on your own computer; samples stay on your machine and nothing is billed per character."],
  ["How much audio do I need to record?", "A few short clips (about a minute in total) read clearly in a quiet room give a good clone. Add more clips for better results."],
  ["Which languages are supported?", "English and many other languages via Chatterbox, plus Telugu, Hindi, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia and Assamese via IndicF5."],
  ["Why is nothing happening when I press Generate?", "This page talks to the engine running on your computer. Make sure it is started (./run_online.sh) and press Retry if you see a connection error. Long scripts can take a few minutes."],
  ["Can I make a podcast with several voices?", "Yes. Start each line with a saved voice name, for example “Ramesh: Welcome to the show!”, and each speaker is voiced separately."],
  ["Can I clone someone else's voice?", "Only with their explicit consent. The studio asks you to confirm consent before saving a voice."],
];

const faqLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQ.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
};

export default function Home() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [langs, setLangs] = useState<Lang[]>([]);
  const [studioUrl, setStudioUrl] = useState("");
  const [voice, setVoice] = useState("");
  const [lang, setLang] = useState("te");
  const [text, setText] = useState("");
  const [translated, setTranslated] = useState("");
  const [translatedFrom, setTranslatedFrom] = useState("");
  const [trModel, setTrModel] = useState("");
  const [expr, setExpr] = useState(0.5);
  const [pace, setPace] = useState(0.5);
  const [busy, setBusy] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [audio, setAudio] = useState("");

  const load = () => {
    setError("");
    Promise.all([api<Voice[]>("/api/voices"), api<Lang[]>("/api/languages"), api<{ studioUrl: string }>("/api/config")])
      .then(([v, l, c]) => {
        setVoices(v);
        setLangs(l);
        setStudioUrl(c.studioUrl);
        if (v.length) setVoice((cur) => cur || v[0].id);
      })
      .catch((e) => setError(e.message));
  };
  useEffect(load, []);

  const langInfo = langs.find((l) => l.code === lang);
  const indian = !!langInfo?.indian;
  const selectedVoice = voices.find((v) => v.id === voice);

  async function translate(): Promise<string> {
    setBusy("Translating…");
    setProgress(0);
    const r = await runJob({ type: "translate", text, lang }, (j) => setProgress(j.progress));
    setTranslated(r?.text || "");
    setTranslatedFrom(text);
    setTrModel(r?.model || "");
    return r?.text || "";
  }

  async function wrap(fn: () => Promise<void>) {
    setError("");
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }

  const onTranslate = () => wrap(async () => { await translate(); });

  const onGenerate = () => wrap(async () => {
    let toSpeak = text;
    if (indian) {
      toSpeak = translated;
      if (looksEnglish(text) && (!translated.trim() || translatedFrom !== text)) toSpeak = await translate();
      if (!toSpeak.trim()) toSpeak = text;
    }
    showAudio("");
    setBusy("Generating audio…");
    setProgress(0);
    const r = await runJob(
      { type: "speak", text: toSpeak, voice, lang, exaggeration: expr, cfg_weight: pace },
      (j) => { setProgress(j.progress); setBusy(j.message || "Generating audio…"); });
    if (!r?.audio) return;
    // The engine deletes the mp3 once it has been sent, so fetch it once and play/download from memory.
    const res = await fetch(r.audio);
    if (!res.ok) throw new Error("The audio link expired — generate again.");
    showAudio(URL.createObjectURL(await res.blob()));
  });

  const showAudio = (url: string) => setAudio((old) => { if (old) URL.revokeObjectURL(old); return url; });

  return (
    <main>
      <header>
        <h1>🎙️ myVoice</h1>
        {studioUrl && <a href={studioUrl} target="_blank" rel="noreferrer">Record / manage voices ↗</a>}
      </header>

      <p className="muted intro">
        Clone your voice once, then turn any text into natural speech — in English or an Indian language. Private and free.
      </p>

      {error && (
        <div className="card error">
          {error} <button onClick={load} style={{ marginLeft: 8 }}>Retry</button>
        </div>
      )}

      <section className="card">
        <div className="row">
          <div>
            <label htmlFor="voice">Voice</label>
            <select id="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
              {voices.length === 0 && <option value="">No voices yet — create one in the studio</option>}
              {voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="lang">Language</label>
            <select id="lang" value={lang} onChange={(e) => setLang(e.target.value)}>
              {langs.map((l) => <option key={l.code} value={l.code}>{l.name}{l.indian ? " · Indian" : ""}</option>)}
            </select>
          </div>
        </div>
        {indian && selectedVoice && !selectedVoice.indic_samples.includes(lang) && (
          <p className="muted">
            Tip: record a short {langInfo?.name} sample for {selectedVoice.name} in the studio (Step 4) for a natural accent.
          </p>
        )}
      </section>

      <section className="card">
        <label htmlFor="text">{indian ? "English text (will be translated)" : "Text or podcast script"}</label>
        <textarea id="text" value={text} onChange={(e) => setText(e.target.value)}
          placeholder={"Paste any length of text.\n\nMulti-voice podcast: start lines with a voice name, e.g.\nRamesh: Welcome to the show!"} />

        {indian && (translated || busy === "Translating…") && (
          <div style={{ marginTop: 14 }}>
            <label htmlFor="translated">{langInfo?.name} text — review &amp; edit before generating</label>
            <textarea id="translated" value={translated} onChange={(e) => setTranslated(e.target.value)} />
            {trModel && <p className="muted">Translated with {trModel}. Fix anything that sounds unnatural.</p>}
            {translated && translatedFrom !== text && (
              <p className="muted">English changed since this translation — Generate will re-translate.</p>
            )}
          </div>
        )}

        {!indian && (
          <details style={{ marginTop: 12 }}>
            <summary>Delivery</summary>
            <div className="row" style={{ marginTop: 8 }}>
              <div>
                <label>Expressiveness: {expr.toFixed(2)}</label>
                <input type="range" min={0.25} max={2} step={0.05} value={expr} onChange={(e) => setExpr(+e.target.value)} />
              </div>
              <div>
                <label>Pace / guidance: {pace.toFixed(2)}</label>
                <input type="range" min={0} max={1} step={0.05} value={pace} onChange={(e) => setPace(+e.target.value)} />
              </div>
            </div>
          </details>
        )}

        <div className="actions">
          {indian && (
            <button onClick={onTranslate} disabled={!!busy || !text.trim()}>🌐 Translate to {langInfo?.name}</button>
          )}
          <button className="primary" onClick={onGenerate} disabled={!!busy || !voice || !(text.trim() || translated.trim())}>
            🔊 Generate
          </button>
        </div>

        {busy && (
          <div style={{ marginTop: 14 }}>
            <p className="muted">{busy} (long scripts take a few minutes)</p>
            <progress value={progress} max={1} />
          </div>
        )}
      </section>

      <section className="card" aria-live="polite">
        <h2>Your audio</h2>
        {audio ? (
          <>
            <p className="ok">Ready — press play to review your voice:</p>
            <audio controls src={audio} aria-label="Generated speech in your voice" />
            <div className="actions"><a href={audio} download="myVoice.mp3">⬇ Download MP3</a></div>
          </>
        ) : (
          <p className="muted">
            Pick a voice, paste some text and press Generate. Your result appears here with a player and download link.
          </p>
        )}
      </section>

      <section className="card" aria-labelledby="setup">
        <h2 id="setup">Get started in 4 steps</h2>
        <ol className="steps">
          <li><strong>Start the engine.</strong> Run <code>./run.sh</code> (or <code>./run_online.sh</code> to use this page).</li>
          <li><strong>Create your voice.</strong> Read the on-screen script into the mic in the studio and save it with consent ticked.</li>
          <li><strong>Add text.</strong> Paste any length of text or a multi-voice script, then choose a language.</li>
          <li><strong>Generate &amp; download.</strong> Listen to the result and download it as MP3.</li>
        </ol>
      </section>

      <section className="card" aria-labelledby="faq">
        <h2 id="faq">FAQ</h2>
        {FAQ.map(([q, a]) => (
          <details key={q} className="faq">
            <summary>{q}</summary>
            <p>{a}</p>
          </details>
        ))}
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqLd) }} />
    </main>
  );
}
