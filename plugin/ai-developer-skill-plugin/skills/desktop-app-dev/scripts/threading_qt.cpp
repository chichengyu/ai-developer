// Qt 6 C++ background work with cancellation + progress + safe UI bridge.
//
// The worker is moved to a dedicated QThread; every UI update crosses the
// thread boundary as a queued signal, so the UI thread never sees a worker
// thread touching widgets directly.
//
// CMake: qt_add_executable(app main.cpp threading_qt.cpp) enables AUTOMOC
// and generates threading_qt.moc for the Q_OBJECT classes below.
//
// Usage:
//   JobThread job(
//       [](auto progress, auto isCancelled) -> QVariant {
//           for (int i = 1; i <= 100; ++i) {
//               if (isCancelled()) throw std::runtime_error("cancelled");
//               progress(i / 100.0);
//               QThread::msleep(50);
//           }
//           return "ok";
//       });
//   QObject::connect(&job, &JobThread::progress, progressBar, &QProgressBar::setValue);
//   QObject::connect(&job, &JobThread::finished, ...);
//   job.start();
//   // later: job.cancel();

#include <QObject>
#include <QString>
#include <QThread>
#include <QVariant>

#include <atomic>
#include <functional>
#include <stdexcept>
#include <utility>

class JobWorker : public QObject {
    Q_OBJECT
public:
    using Job = std::function<QVariant(std::function<void(qreal)>, std::function<bool()>)>;

    explicit JobWorker(Job job, QObject* parent = nullptr)
        : QObject(parent), job_(std::move(job)) {}

public slots:
    void run() {
        try {
            const QVariant result = job_(
                [this](qreal percent) { emit progress(percent); },
                [this]() { return cancel_.load(); });
            if (cancel_.load()) {
                emit cancelled();
            } else {
                emit finished(result);
            }
        } catch (const std::exception& ex) {
            emit failed(QString::fromUtf8(ex.what()));
        } catch (...) {
            emit failed(QStringLiteral("unknown job error"));
        }
        emit completed();
    }

    void cancel() { cancel_.store(true); }

signals:
    void progress(qreal percent);
    void finished(const QVariant& result);
    void failed(const QString& message);
    void cancelled();
    void completed();

private:
    Job job_;
    std::atomic_bool cancel_{false};
};

class JobThread : public QObject {
    Q_OBJECT
public:
    explicit JobThread(JobWorker::Job job, QObject* parent = nullptr)
        : QObject(parent), worker_(new JobWorker(std::move(job))) {
        worker_->moveToThread(&thread_);
        connect(&thread_, &QThread::started, worker_, &JobWorker::run);
        connect(worker_, &JobWorker::completed, &thread_, &QThread::quit);
        connect(worker_, &JobWorker::progress, this, &JobThread::progress);
        connect(worker_, &JobWorker::finished, this, &JobThread::finished);
        connect(worker_, &JobWorker::failed, this, &JobThread::failed);
        connect(worker_, &JobWorker::cancelled, this, &JobThread::cancelled);
    }

    ~JobThread() override {
        cancel();
        thread_.quit();
        thread_.wait();
        delete worker_;
    }

    void start() { thread_.start(); }
    void cancel() { worker_->cancel(); }

signals:
    void progress(qreal percent);
    void finished(const QVariant& result);
    void failed(const QString& message);
    void cancelled();

private:
    QThread thread_;
    JobWorker* worker_;
};

#include "threading_qt.moc"
