/** Profile photo when one is set, otherwise the person's initials. */
export function initialsOf(name = '') {
  return (
    name
      .split(' ')
      .filter(Boolean)
      .map((part) => part[0])
      .slice(0, 2)
      .join('')
      .toUpperCase() || 'U'
  )
}

export default function Avatar({ user, className = 'h-9 w-9', textClassName = 'text-sm' }) {
  if (user?.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.full_name ? `${user.full_name}'s profile photo` : 'Profile photo'}
        className={`${className} shrink-0 rounded-full object-cover ring-1 ring-black/5`}
      />
    )
  }
  return (
    <span
      className={`${className} ${textClassName} flex shrink-0 items-center justify-center rounded-full bg-brand-500 font-semibold text-white`}
      aria-hidden="true"
    >
      {initialsOf(user?.full_name)}
    </span>
  )
}
