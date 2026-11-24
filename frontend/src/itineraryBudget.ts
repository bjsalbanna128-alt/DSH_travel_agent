import type { DayPlan, TripRecord } from './types/travel'

export function itineraryBudget(days: DayPlan[], request?: TripRecord['travel_request']) {
  const travelers = request?.travelers
  const people = Math.max(1, (travelers?.adults ?? 0) + (travelers?.children ?? 0) + (travelers?.elderly ?? 0))
  let tickets = 0
  let hotels = 0
  let meals = 0
  let transport = 0

  for (const day of days) {
    tickets += (day.attractions ?? []).reduce((sum, attraction) => sum + (attraction.ticket_price_cny ?? 0), 0) * people
    hotels += day.hotel?.price_per_night_cny ?? 0
    meals += ((day.lunch?.avg_price_per_person_cny ?? 0) + (day.dinner?.avg_price_per_person_cny ?? 0)) * people
    transport += (day.transport ?? []).reduce((sum, leg) => sum + (leg.price_cny ?? 0), 0) * people
  }
  return { tickets, hotels, meals, transport, total: Math.round((tickets + hotels + meals + transport) * 100) / 100 }
}
