const API_URL = process.env.NEXT_PUBLIC_API_URL;

export interface Character {
  name: string;
  role: string;
  traits: string[];
  current_state: string;
}

export interface StoryBible {
  pov?: string;
  voice_notes?: string;
  characters?: Character[];
  established_facts?: string[];
  open_threads?: string[];
  last_scene_summary?: string;
}

export interface Story {
  id: string;
  title: string;
  original_text: string;
  bible_json: StoryBible;
  created_at: string;
}

export interface Node {
  id: string;
  story_id: string;
  parent_id: string | null;
  content: string;
  bible_snapshot: StoryBible;
  rolling_summary: string;
  created_at: string;
}

export interface Option {
  id: string;
  node_id: string;
  approach_type: "ESCALATE" | "REVEAL" | "QUIET" | "REVERSAL";
  title: string;
  pitch: string;
  was_chosen: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

export function createStory(title: string, text: string): Promise<Story> {
  return request<Story>("/stories/", {
    method: "POST",
    body: JSON.stringify({ title, original_text: text }),
  });
}

/** Stage 1: extract the story bible and create the root node the reader loop starts from. */
export function ingestStory(storyId: string): Promise<{ story: Story; root_node_id: string }> {
  return request(`/stories/${storyId}/ingest`, { method: "POST" });
}

/** Stage 3: propose distinct branch options for what happens next from this node. */
export function getOptions(nodeId: string): Promise<Option[]> {
  return request(`/nodes/${nodeId}/options`, { method: "POST" });
}

/** Stage 4+5: write the chosen continuation and persist it as a new child node. */
export function chooseOption(nodeId: string, optionId: string): Promise<Node> {
  return request(`/nodes/${nodeId}/continue`, {
    method: "POST",
    body: JSON.stringify({ option_id: optionId }),
  });
}

/** Full branch text from the story's original text through this node. */
export function getPath(nodeId: string): Promise<{ text: string }> {
  return request(`/nodes/${nodeId}/path`);
}

/** All nodes for a story, for a branch-tree / rewind view. */
export function getTree(storyId: string): Promise<Node[]> {
  return request(`/stories/${storyId}/tree`);
}
