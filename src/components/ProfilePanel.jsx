import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Camera, Trash2 } from 'lucide-react'
import Avatar from './Avatar'
import { Button, Field } from './ui'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { api } from '../lib/api'
import { ACCEPTED_TYPES, describeFileError, fileToAvatarDataUrl } from '../lib/image'

export default function ProfilePanel() {
  const { user, refreshUser } = useAuth()
  const toast = useToast()
  const fileRef = useRef(null)

  const [form, setForm] = useState({ full_name: '', email: '', phone: '' })
  const [avatar, setAvatar] = useState(null)
  const [avatarTouched, setAvatarTouched] = useState(false)
  const [error, setError] = useState(null)

  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', confirm: '' })
  const [passwordError, setPasswordError] = useState(null)

  useEffect(() => {
    if (!user) return
    setForm({ full_name: user.full_name ?? '', email: user.email ?? '', phone: user.phone ?? '' })
    setAvatar(user.avatar_url ?? null)
    setAvatarTouched(false)
  }, [user])

  const setValue = (key) => (event) => {
    setForm((previous) => ({ ...previous, [key]: event.target.value }))
    setError(null)
  }

  const saveMutation = useMutation({
    mutationFn: (payload) => api('/api/auth/me', { method: 'PUT', body: payload }),
    onSuccess: async () => {
      await refreshUser()
      toast.success('Profile updated')
      setError(null)
      setAvatarTouched(false)
    },
    onError: (saveError) => setError(saveError.message),
  })

  const passwordMutation = useMutation({
    mutationFn: (payload) => api('/api/auth/me/password', { method: 'POST', body: payload }),
    onSuccess: () => {
      toast.success('Password updated')
      setPasswords({ current_password: '', new_password: '', confirm: '' })
      setPasswordError(null)
    },
    onError: (changeError) => setPasswordError(changeError.message),
  })

  const onPickFile = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = '' // let the same file be chosen again after a removal
    if (!file) return

    const problem = describeFileError(file)
    if (problem) {
      setError(problem)
      return
    }
    try {
      setAvatar(await fileToAvatarDataUrl(file))
      setAvatarTouched(true)
      setError(null)
    } catch (conversionError) {
      setError(conversionError.message)
    }
  }

  const removePhoto = () => {
    setAvatar(null)
    setAvatarTouched(true)
    setError(null)
  }

  const saveProfile = () => {
    setError(null)
    if (!form.full_name.trim()) {
      setError('Your name cannot be empty')
      return
    }
    const payload = {
      full_name: form.full_name.trim(),
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
    }
    // Only send the photo when it actually changed — it is the large field.
    if (avatarTouched) payload.avatar_url = avatar
    saveMutation.mutate(payload)
  }

  const savePassword = () => {
    setPasswordError(null)
    if (passwords.new_password.length < 8) {
      setPasswordError('The new password must be at least 8 characters')
      return
    }
    if (passwords.new_password !== passwords.confirm) {
      setPasswordError('The two new passwords do not match')
      return
    }
    passwordMutation.mutate({
      current_password: passwords.current_password,
      new_password: passwords.new_password,
    })
  }

  const dirty =
    avatarTouched ||
    form.full_name !== (user?.full_name ?? '') ||
    form.email !== (user?.email ?? '') ||
    form.phone !== (user?.phone ?? '')

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-base font-semibold text-ink">Your profile</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Your name and photo appear on the sidebar, the top bar and on every receipt you ring up.
        </p>

        <div className="mt-5 flex flex-col gap-6 sm:flex-row sm:items-start">
          <div className="flex flex-col items-center gap-3">
            <Avatar
              user={{ full_name: form.full_name, avatar_url: avatar }}
              className="h-24 w-24"
              textClassName="text-2xl"
            />
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              onChange={onPickFile}
              className="hidden"
            />
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
                <Camera className="h-4 w-4" />
                {avatar ? 'Change' : 'Add photo'}
              </Button>
              {avatar ? (
                <Button variant="ghost" size="sm" onClick={removePhoto} title="Remove photo">
                  <Trash2 className="h-4 w-4" />
                </Button>
              ) : null}
            </div>
            <p className="max-w-[12rem] text-center text-xs text-ink-faint">
              PNG, JPEG or WebP. Cropped square and resized automatically.
            </p>
          </div>

          <div className="grid flex-1 grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Full name" className="sm:col-span-2">
              <input className="field-input" value={form.full_name} onChange={setValue('full_name')} />
            </Field>
            <Field label="Email">
              <input className="field-input" type="email" value={form.email} onChange={setValue('email')} />
            </Field>
            <Field label="Mobile">
              <input className="field-input" value={form.phone} onChange={setValue('phone')} />
            </Field>
            <Field label="Username" hint="Your sign-in name cannot be changed">
              <input className="field-input" value={user?.username ?? ''} disabled />
            </Field>
            <Field label="Role" hint="Only an owner can grant roles">
              <input className="field-input" value={user?.role ?? ''} disabled />
            </Field>
          </div>
        </div>

        {error ? (
          <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" role="alert">
            {error}
          </p>
        ) : null}

        <div className="mt-5 flex gap-2">
          <Button loading={saveMutation.isPending} disabled={!dirty} onClick={saveProfile}>
            Save profile
          </Button>
          <Button
            variant="secondary"
            disabled={!dirty}
            onClick={() => {
              setForm({
                full_name: user?.full_name ?? '',
                email: user?.email ?? '',
                phone: user?.phone ?? '',
              })
              setAvatar(user?.avatar_url ?? null)
              setAvatarTouched(false)
              setError(null)
            }}
          >
            Reset
          </Button>
        </div>
      </section>

      <section className="border-t border-edge pt-6">
        <h2 className="text-base font-semibold text-ink">Change password</h2>
        <p className="mt-1 text-sm text-ink-muted">
          The demo accounts ship with well-known passwords — change yours before real use.
        </p>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Current password">
            <input
              className="field-input"
              type="password"
              autoComplete="current-password"
              value={passwords.current_password}
              onChange={(event) => {
                setPasswords((p) => ({ ...p, current_password: event.target.value }))
                setPasswordError(null)
              }}
            />
          </Field>
          <Field label="New password" hint="At least 8 characters">
            <input
              className="field-input"
              type="password"
              autoComplete="new-password"
              value={passwords.new_password}
              onChange={(event) => {
                setPasswords((p) => ({ ...p, new_password: event.target.value }))
                setPasswordError(null)
              }}
            />
          </Field>
          <Field label="Confirm new password">
            <input
              className="field-input"
              type="password"
              autoComplete="new-password"
              value={passwords.confirm}
              onChange={(event) => {
                setPasswords((p) => ({ ...p, confirm: event.target.value }))
                setPasswordError(null)
              }}
            />
          </Field>
        </div>

        {passwordError ? (
          <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" role="alert">
            {passwordError}
          </p>
        ) : null}

        <div className="mt-5">
          <Button
            loading={passwordMutation.isPending}
            disabled={!passwords.current_password || !passwords.new_password || !passwords.confirm}
            onClick={savePassword}
          >
            Update password
          </Button>
        </div>
      </section>
    </div>
  )
}
