-- Trigger-only SECURITY DEFINER function must not be callable through PostgREST RPC.
REVOKE ALL ON FUNCTION public.notify_projection_event() FROM PUBLIC, anon, authenticated;
