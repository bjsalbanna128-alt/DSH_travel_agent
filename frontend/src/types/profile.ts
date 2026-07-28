export interface UserProfile {
  user_id: string
  interest_tags: string[]
  pace_preference: 'relaxed' | 'moderate' | 'intensive'
  preferred_hotel_stars: number
  cuisine_preferences: string[]
  dietary_restrictions: string[]
  avg_budget_per_day_cny: number
  frequent_destinations: { city: string; count: number }[]
  feedback_scores: number[]
  travel_count: number
  updated_at: string
}
