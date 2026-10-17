import { useState, useEffect, useRef } from 'react';

// A tiny 1-pixel transparent MP4 data URI used for the NoSleep fallback shim
const NO_SLEEP_VIDEO_URI = 'data:video/mp4;base64,AAAAHGZ0eXBpc29tAAACAGlzb21pc28yYXZjMQAAAAhmcmVlAAAAG21kYXQAAAGzABAHAAABthAHAAABt4AAAASaAAAAE21vb3YAAABsbXZoZAAAAADawdcr2sHXKwAAA+gAAD6AAAEAAAEAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAcbWlhZgAAAAAAAAABQAAAHm1pYWYAAAAAAAAAAgAAAAxtaWFmAAAAAAADAAAALW1pYWgAAAAAABAAAAABAAAAAgAAAAMAAAAOAAABOAAAATQAAAEoAAAAuHRyYWsAAABcdGtoZAAAAADawdcr2sHXKwAAAAEAAAAAAAD6AAAAAQAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAJZWR0cwAAABxlZWxzdAAAAAABAAAD6AAAAAAAABAAAAAAAqhtZGlhAAAAIG1kaGQAAAAA2sHXK9rB1ysAAAPoAAA+gAAAAAAAAAAudWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABrm1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAAVRzdGJsAAAArHN0c2QAAAAAAAAAAQAAAJhhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAEAAQASAAAAASAAABIAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABj//wAAADZiYnRycnQAAAAAAAAB9AAAAAAAEAAAAAAQAAAAABAAAAAAEQAAAAARAAAAABIAAAAUc3R0cwAAAAAAAAABAAAAAQAAADoAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAAAAEAAAABAAAAAQAAAAEAAAAUc3RzejAAAAAAAAAAAAAAAQAAABAAAAAUc3RjbwAAAAAAAAABAAAALg==';

export function useScreenWakeLock() {
  const [isLocked, setIsLocked] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const wakeLockRef = useRef<any>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    // 1. Try native WakeLock API
    const requestNativeWakeLock = async () => {
      try {
        if ('wakeLock' in navigator) {
          wakeLockRef.current = await (navigator as any).wakeLock.request('screen');
          setIsLocked(true);
          
          wakeLockRef.current.addEventListener('release', () => {
            setIsLocked(false);
          });
          return true;
        }
      } catch (err) {
        console.warn('WakeLock API failed or denied', err);
      }
      return false;
    };

    const enableLock = async () => {
      const nativeSuccess = await requestNativeWakeLock();
      
      // 2. Fallback to NoSleep Video Shim if native fails
      if (!nativeSuccess) {
        if (!videoRef.current) {
          const video = document.createElement('video');
          video.setAttribute('playsinline', '');
          video.setAttribute('muted', '');
          video.setAttribute('loop', '');
          video.src = NO_SLEEP_VIDEO_URI;
          video.style.display = 'none';
          document.body.appendChild(video);
          videoRef.current = video;
        }

        try {
          await videoRef.current.play();
          setIsLocked(true);
        } catch (e) {
          console.warn('NoSleep video shim failed (requires user interaction)', e);
          // 3. UI Text Fallback
          setUnsupported(true);
        }
      }
    };

    // Browsers often require a user interaction to start video or wake lock,
    // so we expose this as a function to be called on button click, but we
    // can also try it proactively.
    
    // Cleanup
    return () => {
      if (wakeLockRef.current) {
        wakeLockRef.current.release().catch(console.error);
        wakeLockRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.pause();
        videoRef.current.remove();
        videoRef.current = null;
      }
    };
  }, []);

  return { isLocked, unsupported };
}
