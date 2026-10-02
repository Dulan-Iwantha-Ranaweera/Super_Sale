import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

/** Store profile + preferences. Cached app-wide so every screen formats money the same way. */
export function useStoreSettings() {
  return useQuery({
    queryKey: ['store'],
    queryFn: () => api('/api/store'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCurrency() {
  const { data } = useStoreSettings()
  return data?.currency ?? 'LKR'
}
