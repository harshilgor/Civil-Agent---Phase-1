import { create } from "zustand";
import type { JobSummary, PipelineResults } from "@/api/types";

type JobState = {
  job: JobSummary | null;
  results: PipelineResults | null;
  setJob: (j: JobSummary | null) => void;
  setResults: (r: PipelineResults | null) => void;
};

export const useJobStore = create<JobState>((set) => ({
  job: null,
  results: null,
  setJob: (job) => set({ job }),
  setResults: (results) => set({ results }),
}));
