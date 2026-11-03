import { GUIDE, type Copy, type GuideEntry } from "./content";

interface GuideTopic {
  entry: GuideEntry;
  chapterTitle: Copy;
}

export function guideTopics(chapterId: string): GuideTopic[] {
  const chapter = GUIDE.find(({ id }) => id === chapterId);
  return chapter?.entries.map((entry) => ({ entry, chapterTitle: chapter.title })) ?? [];
}

export function searchGuideTopics(query: string): GuideTopic[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [];
  return GUIDE.flatMap((chapter) => chapter.entries
    .filter((entry) => [chapter.title, entry.title, entry.body, ...(entry.steps ?? [])]
      .flat().join(" ").toLocaleLowerCase().includes(needle))
    .map((entry) => ({ entry, chapterTitle: chapter.title })));
}

export function selectedGuideTopic(topics: readonly GuideTopic[], topicId?: string) {
  return topics.find(({ entry }) => entry.id === topicId) ?? topics[0];
}
