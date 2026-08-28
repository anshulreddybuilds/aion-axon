import { useEffect, useRef, useState } from "react";
import { createRecognizer, speechRecognitionSupported } from "./speechRecognition.js";

/**
 * React hook wrapper around speechRecognition.js. Builds the recognizer
 * exactly ONCE (empty effect dependency array) and reads onText/onError
 * from refs updated every render -- the exact fix Command.jsx's <Speech>
 * needed after depending on [onText] tore recognition down mid-listen.
 * A component that re-renders on every keystroke or poll tick (AppV4.jsx
 * does both) would reproduce that bug immediately without this.
 */
export function useSpeechInput({ onText, onError }) {
  const [listening, setListening] = useState(false);
  const [supported] = useState(() => speechRecognitionSupported());
  const recognitionRef = useRef(null);
  const onTextRef = useRef(onText);
  const onErrorRef = useRef(onError);

  onTextRef.current = onText;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!supported) return;

    recognitionRef.current = createRecognizer({
      onText: (transcript) => onTextRef.current?.(transcript),
      onError: (message) => {
        setListening(false);
        onErrorRef.current?.(message);
      },
      onEnd: () => setListening(false),
    });

    return () => {
      try {
        recognitionRef.current?.abort();
      } catch {
        /* already stopped */
      }
    };
  }, [supported]);

  const toggle = () => {
    if (!recognitionRef.current) return;

    if (listening) {
      recognitionRef.current.stop();
      setListening(false);
      return;
    }

    try {
      recognitionRef.current.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  };

  return { listening, supported, toggle };
}
