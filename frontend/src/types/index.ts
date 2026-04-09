// User
export interface User {
  id: string
  email: string
  nickname?: string
  created_at: string
}

export interface TokenOut {
  access_token: string
  token_type: string
  user: User
}

// Project
export interface Project {
  id: string
  user_id: string
  name: string
  description?: string
  status: string
  created_at: string
  updated_at: string
}

// Guide
export interface Question {
  step: number
  total_steps: number
  question_text: string
  question_type: 'single_choice' | 'text_input'
  options?: string[]
}

export interface GuideSession {
  id: string
  project_id: string
  answers: Record<string, string>
  brief?: Record<string, string>
  step: number
  completed: boolean
}

// Script
export interface ScriptSection {
  id: number
  title: string
  content: string
  duration_estimate: string
}

export interface ScriptContent {
  title: string
  hook: string
  sections: ScriptSection[]
  cta: string
  total_duration_estimate: string
  notes: string
}

export interface Script {
  id: string
  project_id: string
  version: number
  format: string
  content: ScriptContent
  is_latest: boolean
  created_at: string
}

// Video
export interface Video {
  id: string
  project_id: string
  filename: string
  source: string
  storage_path?: string
  duration?: number
  created_at: string
}

// Clip Job
export interface ClipSegment {
  id: number
  start: number
  end: number
  duration: number
  transcript: string
}

export interface ClipPlan {
  segments: ClipSegment[]
  total_scenes: number
}

export interface ClipJob {
  id: string
  project_id: string
  video_id: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  clip_plan?: ClipPlan
  progress: number
  output_path?: string
  error_msg?: string
  created_at: string
  updated_at: string
}

// WebSocket progress
export interface ClipProgress {
  progress: number
  message: string
}
