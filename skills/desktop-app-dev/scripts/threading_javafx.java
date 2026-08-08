// JavaFX background work with cancellation + progress + safe UI bridge.
//
// JavaFX Task already owns progress/state properties. Its call() method
// runs on a background thread; `updateProgress` / `updateMessage` are
// thread-safe, and listeners are marshalled with Platform.runLater.
//
// Usage:
//   Task<String> task = new Task<>() {
//       @Override protected String call() throws Exception {
//           for (int i = 1; i <= 100; i++) {
//               if (isCancelled()) break;
//               Thread.sleep(50);
//               updateProgress(i, 100);
//           }
//           return "ok";
//       }
//   };
//   BackgroundJob.start(task,
//       () -> progressBar.setProgress(task.getProgress()),
//       result -> statusLabel.setText("done: " + result),
//       error -> statusLabel.setText("error: " + error.getMessage()),
//       () -> statusLabel.setText("cancelled"));
//   // later: task.cancel();

import javafx.application.Platform;
import javafx.concurrent.Task;

import java.util.function.Consumer;

public final class BackgroundJob {
    private BackgroundJob() {
    }

    public static <T> Task<T> start(
            Task<T> task,
            Runnable onProgress,
            Consumer<T> onDone,
            Consumer<Throwable> onError,
            Runnable onCancel) {
        task.progressProperty().addListener(
                (observable, oldValue, newValue) -> Platform.runLater(onProgress));
        task.setOnSucceeded(event -> onDone.accept(task.getValue()));
        task.setOnFailed(event -> onError.accept(task.getException()));
        task.setOnCancelled(event -> onCancel.run());

        Thread thread = new Thread(task);
        thread.setDaemon(true);
        thread.start();
        return task;
    }
}
