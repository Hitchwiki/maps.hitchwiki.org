package org.hitchwiki.maps.data
import android.content.Context
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import org.hitchwiki.maps.db.HitchwikiDb

actual class DatabaseDriverFactory(private val context: Context) {
    actual fun create(): SqlDriver = AndroidSqliteDriver(HitchwikiDb.Schema, context, "hitchwiki.db")
}
