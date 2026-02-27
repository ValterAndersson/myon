const admin = require('firebase-admin');

/**
 * Centralized Firestore operations helper
 * Mirrors the FirebaseServiceProtocol from Swift codebase
 */
class FirestoreHelper {
  constructor() {
    // Initialize Firebase Admin if not already initialized
    if (!admin.apps.length) {
      admin.initializeApp();
    }
    this.db = admin.firestore();
  }

  // Basic document operations
  async getDocument(collection, documentId) {
    try {
      const doc = await this.db.collection(collection).doc(documentId).get();
      if (!doc.exists) {
        return null;
      }
      return { id: doc.id, ...doc.data() };
    } catch (error) {
      console.error(`Error getting document ${collection}/${documentId}:`, error);
      throw error;
    }
  }

  async getDocuments(collection, queryParams = null) {
    try {
      let query = this.db.collection(collection);
      
      if (queryParams) {
        if (queryParams.where) {
          queryParams.where.forEach(condition => {
            query = query.where(condition.field, condition.operator, condition.value);
          });
        }
        if (queryParams.orderBy) {
          query = query.orderBy(queryParams.orderBy.field, queryParams.orderBy.direction);
        }
        if (queryParams.limit) {
          query = query.limit(queryParams.limit);
        }
        if (queryParams.startAfter) {
          query = query.startAfter(queryParams.startAfter);
        }
      }

      const snapshot = await query.get();
      return snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
    } catch (error) {
      console.error(`Error getting documents from ${collection}:`, error);
      throw error;
    }
  }

  async addDocument(collection, data) {
    try {
      const docRef = await this.db.collection(collection).add({
        ...data,
        created_at: admin.firestore.FieldValue.serverTimestamp(),
        updated_at: admin.firestore.FieldValue.serverTimestamp()
      });
      return docRef.id;
    } catch (error) {
      console.error(`Error adding document to ${collection}:`, error);
      throw error;
    }
  }

  async updateDocument(collection, documentId, data) {
    try {
      await this.db.collection(collection).doc(documentId).update({
        ...data,
        updated_at: admin.firestore.FieldValue.serverTimestamp()
      });
      return true;
    } catch (error) {
      console.error(`Error updating document ${collection}/${documentId}:`, error);
      throw error;
    }
  }

  async upsertDocument(collection, documentId, data) {
    try {
      const ref = this.db.collection(collection).doc(documentId);
      const snap = await ref.get();
      const now = admin.firestore.FieldValue.serverTimestamp();
      const payload = { ...data, updated_at: now };
      if (!snap.exists) {
        payload.created_at = now;
      }
      await ref.set(payload, { merge: true });
      return true;
    } catch (error) {
      console.error(`Error upserting document ${collection}/${documentId}:`, error);
      throw error;
    }
  }

  async deleteDocument(collection, documentId) {
    try {
      await this.db.collection(collection).doc(documentId).delete();
      return true;
    } catch (error) {
      console.error(`Error deleting document ${collection}/${documentId}:`, error);
      throw error;
    }
  }

  // Subcollection operations
  async getDocumentFromSubcollection(parentCollection, parentDocumentId, subcollection, documentId) {
    try {
      const doc = await this.db
        .collection(parentCollection)
        .doc(parentDocumentId)
        .collection(subcollection)
        .doc(documentId)
        .get();
      
      if (!doc.exists) {
        return null;
      }
      return { id: doc.id, ...doc.data() };
    } catch (error) {
      console.error(`Error getting subcollection document:`, error);
      throw error;
    }
  }

  async getDocumentsFromSubcollection(parentCollection, parentDocumentId, subcollection, queryParams = null) {
    try {
      let query = this.db
        .collection(parentCollection)
        .doc(parentDocumentId)
        .collection(subcollection);
      
      if (queryParams) {
        if (queryParams.where) {
          queryParams.where.forEach(condition => {
            query = query.where(condition.field, condition.operator, condition.value);
          });
        }
        if (queryParams.orderBy) {
          query = query.orderBy(queryParams.orderBy.field, queryParams.orderBy.direction);
        }
        if (queryParams.limit) {
          query = query.limit(queryParams.limit);
        }
      }

      // Default safety limit to prevent unbounded reads
      if (!queryParams?.limit) {
        query = query.limit(500);
      }

      const snapshot = await query.get();
      return snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
    } catch (error) {
      console.error(`Error getting documents from subcollection:`, error);
      throw error;
    }
  }

  async addDocumentToSubcollection(parentCollection, parentDocumentId, subcollection, data) {
    try {
      const docRef = await this.db
        .collection(parentCollection)
        .doc(parentDocumentId)
        .collection(subcollection)
        .add({
          ...data,
          created_at: admin.firestore.FieldValue.serverTimestamp(),
          updated_at: admin.firestore.FieldValue.serverTimestamp()
        });
      return docRef.id;
    } catch (error) {
      console.error(`Error adding document to subcollection:`, error);
      throw error;
    }
  }

  async updateDocumentInSubcollection(parentCollection, parentDocumentId, subcollection, documentId, data) {
    try {
      await this.db
        .collection(parentCollection)
        .doc(parentDocumentId)
        .collection(subcollection)
        .doc(documentId)
        .update({
          ...data,
          updated_at: admin.firestore.FieldValue.serverTimestamp()
        });
      return true;
    } catch (error) {
      console.error(`Error updating document in subcollection:`, error);
      throw error;
    }
  }

  async upsertDocumentInSubcollection(parentCollection, parentDocumentId, subcollection, documentId, data) {
    try {
      const ref = this.db
        .collection(parentCollection)
        .doc(parentDocumentId)
        .collection(subcollection)
        .doc(documentId);
      const snap = await ref.get();
      const now = admin.firestore.FieldValue.serverTimestamp();
      const payload = { ...data, updated_at: now };
      if (!snap.exists) payload.created_at = now;
      await ref.set(payload, { merge: true });
      return true;
    } catch (error) {
      console.error(`Error upserting document in subcollection:`, error);
      throw error;
    }
  }

  async deleteDocumentFromSubcollection(parentCollection, parentDocumentId, subcollection, documentId) {
    try {
      await this.db
        .collection(parentCollection)
        .doc(parentDocumentId)
        .collection(subcollection)
        .doc(documentId)
        .delete();
      return true;
    } catch (error) {
      console.error(`Error deleting document from subcollection:`, error);
      throw error;
    }
  }

  // Helper methods for date queries
  createDateRange(startDate, endDate) {
    const start = new Date(startDate);
    const end = new Date(endDate);
    return {
      where: [
        { field: 'created_at', operator: '>=', value: start },
        { field: 'created_at', operator: '<=', value: end }
      ]
    };
  }

  // Helper for text search (limited Firestore capability)
  createTextSearch(field, searchTerm) {
    const searchEnd = searchTerm.replace(/.$/, c => String.fromCharCode(c.charCodeAt(0) + 1));
    return {
      where: [
        { field: field, operator: '>=', value: searchTerm },
        { field: field, operator: '<', value: searchEnd }
      ]
    };
  }
}

module.exports = FirestoreHelper; 