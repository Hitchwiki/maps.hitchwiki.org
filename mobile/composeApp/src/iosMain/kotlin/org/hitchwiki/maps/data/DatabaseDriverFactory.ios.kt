package org.hitchwiki.maps.data
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.native.NativeSqliteDriver
import org.hitchwiki.maps.db.HitchwikiDb

actual class DatabaseDriverFactory {
    actual fun create(): SqlDriver = NativeSqliteDriver(HitchwikiDb.Schema, "hitchwiki.db")
}
